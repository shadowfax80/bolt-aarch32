import json,struct,sys
from pathlib import Path
from collections import defaultdict
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'scripts'),str(root/'scripts/pi4')]
from counter_identity import check_capture,converter
from measurement_records import parse_measurements
from profile_identity import sha256
out=root/'out/r35'; d=out/'counter'; rows=[]
for variant,checksum in [(0,'0x2f744325'),(2,'0x5806b01f')]:
    dump=d/f'stair{variant}.counters.bin'
    capture,ctx,funcs=check_capture(str(dump)+'.manifest.json',dump,d/'cspgo_thinlto.elf',d/'cspgo_thinlto.instr.elf',d/'cspgo_thinlto.instr.funcmap',out/'toolproof',root/'overlay/llvm/patches/atfe',out/'replay-final.json')
    log=Path(capture['evidence'])/'capture.log'; assert sha256(log)==capture['log_sha256']
    text=log.read_text(); measured=parse_measurements(text,f'bolt_bench stair 0 {variant}',['stair'],1)
    assert measured[0]['acc']==checksum
    layout=capture['build']['metadata']['counter_layout']; raw=dump.read_bytes()
    counts=list(struct.unpack_from('<'+str(layout['count'])+'Q',raw,layout['locations']-layout['address']))
    assert len(funcs)==1
    f=funcs[0]; graph=converter().Graph(f,counts,{})
    incoming=defaultdict(int); outgoing=defaultdict(int); leaves={n.node:counts[n.counter] for n in f.leaf_nodes}
    for e,c in zip(f.edges,graph.edge_freqs): incoming[e.to_node]+=c; outgoing[e.from_node]+=c
    nodes=set(incoming)|set(outgoing)|set(leaves)
    entry_nodes=nodes-set(e.to_node for e in f.edges)
    assert len(entry_nodes)==1
    terminal_nodes=nodes-set(e.from_node for e in f.edges)
    for n in nodes-entry_nodes-terminal_nodes:
        assert incoming[n]==(leaves[n] if n in leaves else outgoing[n]),(n,incoming[n],outgoing[n],leaves.get(n))
    entries=sum(outgoing[n] for n in entry_nodes); exits=sum(leaves[n] if n in leaves else incoming[n] for n in terminal_nodes)
    assert entries==exits==1600,(entries,exits)
    branch=[dict(source_offset=hex(e.from_loc.offset),target_offset=hex(e.to_loc.offset),count=c,counter=e.counter) for e,c in zip(f.edges,graph.edge_freqs) if e.from_loc.offset==0x9e10]
    assert len(branch)==2
    expected={0x9e12:1600 if variant==0 else 0,0x9e1a:0 if variant==0 else 1600}
    assert {int(e['target_offset'],16):e['count'] for e in branch}==expected,branch
    rows.append(dict(variant=variant,checksum=checksum,workload_records=measured,capture_manifest_sha256=sha256(str(dump)+'.manifest.json'),entries=entries,exits=exits,early_return_edges=branch,all_internal_flow_conserved=True))
(out/'counter-flow.json').write_text(json.dumps(dict(passed=True,scope='Exact sealed CS stair counts and command-framed output; source-derived 100 warmups + 1500 calls. Output agreement is not an independent algorithmic oracle.',rows=rows),indent=2)+'\n')
print(json.dumps(rows,indent=2))
