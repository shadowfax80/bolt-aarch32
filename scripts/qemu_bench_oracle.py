#!/usr/bin/env python3
"""Independent uint32 arithmetic model for one explicitly approved LK fixture.

Unknown input images must obtain a reviewed source/configuration contract rather
than learning expected values from their own baseline execution.
"""
from functools import lru_cache

MASK = 0xffffffff
CONTRACTS = {
    'e13fa5f45c1b9f970ac29221b15b6efad73c490e291cebd9b06493704f20db20': {
        'name': 'reserved-integer-arm-20261004',
        'platform': 'qemu-virt',
        'bench_source_sha256': 'dec4cca0ca0bb0c45e9ed85d166e3b66ad3363638ae781fe32bd8c20b65b5087',
        'composite_source_sha256': 'a42b1249a8ce739a64b6a9a7086352d5f1d0dfaef0a51a12b06f1c305e873f29',
        'rules_sha256': 'ea8c49a2d016ee24fab40ccd439cac077cf02922ad75c7681834e9b198719bad',
        'configuration': 'benchmark -mfpu=none, -marm; explicit __thumb__ macro retains IT arithmetic; STAIR_M=10, STAIR_X=0, input variant=0',
    },
    # Approved by the user 2026-10-04 (docs/PI4_ORACLE_CONTRACT_DRAFT.md).
    # Source hashes are over LF-normalized text; the build copy has CRLF.
    '424606a869c34b5be5f3c97f66a9cec8ea16844ac788c14c77839edcfef2459b': {
        'name': 'full-lk-rpi4-bolt-test-20261004',
        'platform': 'pi4',
        'bench_source_sha256': 'a48247945d47b359c04f40883361b72c1be87a4a7983aecc299d7c121d0d96d0',
        'composite_source_sha256': '8d830b9ca2a3884270f81cc3b00811f16d6744d5ac838d754664e2ec0ea12adb',
        'rules_sha256': 'c34149eda9808d114cdc8da415a0863ed5de2d2effa3de3c133ed385d3b5a38e',
        'configuration': 'LK rpi4-bolt-test (ARM_CPU_CORTEX_A15, Thumb-2 kernel); bolt_bench -marm, WITH_BOLT_PGO off; STAIR_M=10, STAIR_X=0, input variant=0; 0 FP/NEON instructions',
    },
    # Approved by the user 2026-10-04: R17 stage-1 bolt_edge image
    # (fixtures/lk-rpi4-bolt-edge-0895d7bc.elf). bolt_bench sources equal the
    # full-LK contract's; the 68 bolt_edge sinks come from the generator's
    # Python models (docs/bolt_edge/manifest.json, LF-normalized hashes).
    '0895d7bc1b0dcaa7b60869fd0e3182b6c8cb9a32aebb742c6e5336dd468208dd': {
        'name': 'bolt-edge-stage1-20261004',
        'platform': 'pi4',
        'bench_source_sha256': 'a48247945d47b359c04f40883361b72c1be87a4a7983aecc299d7c121d0d96d0',
        'composite_source_sha256': '8d830b9ca2a3884270f81cc3b00811f16d6744d5ac838d754664e2ec0ea12adb',
        'rules_sha256': 'c34149eda9808d114cdc8da415a0863ed5de2d2effa3de3c133ed385d3b5a38e',
        'edge_manifest': 'docs/bolt_edge/stage1/manifest.json',
        'edge_generator': 'docs/bolt_edge/stage1/gen.py',
        'edge_manifest_sha256': 'dbc9835fd35ab6adde8379240dc024061ab5e8b23035b1c9b3699d64b502a565',
        'edge_generator_sha256': 'ca2d98b7a9986ee8200e89fbc751b45eb22351ae4b2984c16fe204e19bc9b3f9',
        'configuration': 'LK rpi4-bolt-edge (rpi4-bolt-test + generated app/bolt_edge, -mfpu=none); bolt_bench as in the full-LK contract; 0 FP/NEON instructions',
    },
    # Approved by the user 2026-10-04: R17 stage 1b (98 cases; adds the
    # whole-module -marm/-mthumb C builds). fixtures/lk-rpi4-bolt-edge-439dfd7c.elf.
    '439dfd7c8dc660b1b4b8d4bae967750fe87485647460c791e2b7e385304e7bb9': {
        'name': 'bolt-edge-stage1b-20261004',
        'platform': 'pi4',
        'bench_source_sha256': 'a48247945d47b359c04f40883361b72c1be87a4a7983aecc299d7c121d0d96d0',
        'composite_source_sha256': '8d830b9ca2a3884270f81cc3b00811f16d6744d5ac838d754664e2ec0ea12adb',
        'rules_sha256': 'c34149eda9808d114cdc8da415a0863ed5de2d2effa3de3c133ed385d3b5a38e',
        'edge_manifest': 'docs/bolt_edge/stage1b/manifest.json',
        'edge_generator': 'docs/bolt_edge/stage1b/gen.py',
        'edge_manifest_sha256': 'bb4ee4798155bd832af344e09d49d104d9941db7498925cfef175cc7c60945ba',
        'edge_generator_sha256': '7d3fd37f382655d74b8d73f8dc149a1d3c444707718d7792b1618a06e0933cba',
        'configuration': 'LK rpi4-bolt-edge with app/bolt_edge/marm (-marm) and mthumb (-mthumb) submodules, -mfpu=none; bolt_bench as in the full-LK contract; 0 FP/NEON instructions',
    },
}


def u(value):
    return value & MASK


def stair_step(x,state,site):
    state=u(state*1664525+1013904223)
    t=u(x)
    if state>>24 < (5 if site&1 else 250):
        t=u(t*0x9e3779b1);t^=t>>15;t=u(t+(state>>8))
        t=u(t*0x85ebca6b);t^=t>>13;t=u((t<<5)|(t>>27))
        t^=state;t=u(t*0xc2b2ae35);t^=t>>16;t=u(t+0x1234567)
        t=u((t^(t>>7))*0x27d4eb2f);t^=state>>3
        t=u(t*0x165667b1);t^=t>>11
        return u(t+1),state
    t^=0xa5a5a5a5;t=u(t+(state<<3));t=u(t*0xd3a2646c);t^=t>>12
    t=u((t<<9)|(t>>23));t=u(t+state);t=u(t*0xfd7046c5);t^=t>>14
    t=u(t-0x7654321);t=u((t^(t>>5))*0xb55a4f09);t^=state>>6
    t=u(t*0x6c078965);t^=t>>9
    return u(t+2),state


def stair_result():
    # Only selector bits 0/1 in each nibble execute. Cold sites retain their
    # initial state. Warm-up and timed loops each restart their iteration index.
    sites=[k for k in range(640) if k%4<2]
    states={k:u(k*2654435761+12345) for k in sites};acc=0
    for i in (*range(100),*range(1500)):
        x=u(acc+i);acc=x
        for k in sites:
            value,states[k]=stair_step(u(x+k*0x9e37),states[k],k)
            acc^=value
    return acc


@lru_cache(maxsize=1)
def reference_results():
    """Derive values from reviewed source operations, never captured outputs."""
    n=1000000;calls=20000
    results={
        'hot_loop':u(n*(n-1)//2),
        'hot_cold':u(sum(range(0xfffff,n,0x100000))),
        'branch_chain':u(sum(((i^(i>>3))&0xffff).bit_count() for i in range(n))),
        'far_call':0x12345678^0xa53c79d1,
        'it_cond':(2<<24)^(2*n),
    }
    hash_value=2166136261
    for i in range(4096):hash_value=u((hash_value^((i*37+11)&255))*16777619)
    results['memcpy']=hash_value
    acc=sum(4*i+7 for i in range(10000))
    results['interwork']=u(acc+3*u(acc+7))
    def pick(x):
        return (x^0x1111,3*x+1,~x,x<<2,x>>1,x&0xff00,x|0x8000,x-0x99)[x%8]
    results['switch']=u(sum(pick(i) for i in range(n)))
    results['spill_ret']=u(sum(8*i+21 for i in range(100000)))
    results['litpool']=u(sum(0xdeadbeef^i for i in range(n)))
    results['indirect_call']=u(sum(i+101 if i%20 else i*5+3 for i in range(calls)))
    results['interwork_tail']=u(sum(i^0xc0ffee for i in range(calls)))
    def pressure(seed):
        a=seed;b=u(seed*3+1);c=seed^0xabcd;d=u(seed<<2);e=seed>>1
        f=u(a+b);g=u(b+c);h=u(c+d);i=u(d+e);j=u(e+a)
        k=f^g;l=g^h;m=h^i;nn=i^j;o=j^f
        p=u(k+l+m);q=u(m+nn+o);r=u(nn+o+k);s=u(o+k+l)
        return u(sum((a,b,c,d,e,f,g,h,i,j,k,l,m,nn,o,p,q,r,s)))
    results['regpressure']=u(sum(pressure(i) for i in range(calls)))
    results['hotcold_split']=u(n*n-sum(2*i+1 for i in range(0x3ffff,n,0x40000)))
    def icf(x):return u(x*2654435761)^(x>>13)^0x9e3779b9
    results['icf']=u(sum(icf(i)+icf(i^1) for i in range(calls)))
    acc=n*(n-1)//2
    for i in range(0xfff,n,0x1000):
        r=i^(i+1);r=u(r+i+2);r^=i+3;r=u(r+i+4);r^=i+5
        r=u(r+i+6);r^=i+7;acc+=r-i
    results['shrinkwrap']=u(acc)
    results['composite']=u(sum((u(i*2654435761)^(i>>15))+u(i<<1) for i in range(n)))
    results['stair']=stair_result()
    return {name:f'0x{value:08x}' for name,value in results.items()}


def check_contract(image_sha256,platform='qemu-virt'):
    if image_sha256 not in CONTRACTS or CONTRACTS[image_sha256]['platform']!=platform:
        raise ValueError('no reviewed independent oracle contract for input image')
    return CONTRACTS[image_sha256]


def check_edge_results(image_sha256,text,platform='pi4'):
    """R17: when the contract binds a bolt_edge manifest, every case of exactly
    one complete `bolt_edge all` run in `text` must equal the manifest's
    model-computed sink. Returns None for contracts without bolt_edge."""
    import hashlib,json,re
    from pathlib import Path
    contract=check_contract(image_sha256,platform)
    if 'edge_manifest_sha256' not in contract:
        return None
    root=Path(__file__).resolve().parents[1]
    # Each contract names its frozen manifest and generator: later generator
    # versions do not change an approved image's expectations.
    raw=(root/contract['edge_manifest']).read_bytes().replace(b'\r\n',b'\n')
    gen=(root/contract['edge_generator']).read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(raw).hexdigest()!=contract['edge_manifest_sha256'] or \
            hashlib.sha256(gen).hexdigest()!=contract['edge_generator_sha256']:
        raise ValueError('bolt_edge manifest/generator differs from the reviewed contract')
    cases=json.loads(raw)['cases']
    done=re.findall(r'bolt_edge: done (\d+) cases',text)
    if done!=[str(len(cases))]:
        raise ValueError('expected exactly one complete bolt_edge run')
    seen=re.findall(r'bolt_edge: (\w+) sink=(0x[0-9a-f]{8})',text)
    if len(seen)!=len(cases) or dict(seen)!={c['name']:c['expected_sink'] for c in cases}:
        wrong=[c['name'] for c in cases if dict(seen).get(c['name'])!=c['expected_sink']]
        raise ValueError('bolt_edge oracle mismatch: '+','.join(wrong or ['unexpected cases']))
    return {'input_sha256':image_sha256,'contract':contract['name'],'matched_cases':len(cases),
            'scope':'generator-model sinks for approved bolt_edge input; not execution/state proof'}


def check_results(image_sha256,actual,platform='qemu-virt'):
    contract=check_contract(image_sha256,platform)
    expected=reference_results()
    if actual!=expected:
        wrong=[name for name,value in expected.items() if actual.get(name)!=value]
        raise ValueError('independent workload oracle mismatch: '+','.join(wrong or ['unexpected workload']))
    return {'input_sha256':image_sha256,'contract':contract,
            'expected':expected,'matched_workloads':len(expected),
            'scope':'independent sink arithmetic for approved input; not execution/state, PMU or clean-build proof'}
