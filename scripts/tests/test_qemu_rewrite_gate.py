"""Admission and CPU-state faults must reject plausible output-only success."""
from pathlib import Path
import struct,sys,unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qemu_rewrite_gate as gate


def image(candidate=False):
    blob=bytearray(0x1800); blob[:7]=b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HHIIIIIHHHHHH',blob,16,2,40,1,0x1000,52,0x1400,0,52,32,1,40,6,3)
    struct.pack_into('<8I',blob,52,1,0x100,0x1000,0x1000,0x1040,0x1100,5,4)
    strings=b'\0f\0__bolt_reserved_start\0__bolt_reserved_end\0_end\0'
    names=b'\0'+(b'.bolt.org.text' if candidate else b'.text')+b'\0'+(b'.text' if candidate else b'.bolt.reserve')+b'\0.shstrtab\0.strtab\0.symtab\0'
    blob[0x1200:0x1200+len(strings)]=strings; blob[0x1280:0x1280+len(names)]=names
    symbols=[(1,0x2000 if candidate else 0x1000,8,0x12,0,2 if candidate else 1),
             (strings.index(b'__bolt_reserved_start'),0x2000,0,0x10,0,2),
             (strings.index(b'__bolt_reserved_end'),0x2040,0,0x10,0,2),
             (strings.index(b'_end'),0x2100,0,0x10,0,0xfff1)]
    for i,row in enumerate(symbols,1): struct.pack_into('<IIIBBH',blob,0x1300+i*16,*row)
    text_name=1; reserve_name=names.find(b'\0',1)+1
    headers=[(0,)*10,(text_name,1,6,0x1000,0x100,8,0,0,4,0),
             (reserve_name,1,6,0x2000,0x1100,64,0,0,4,0),
             (names.index(b'.shstrtab'),3,0,0,0x1280,len(names),0,0,1,0),
             (names.index(b'.strtab'),3,0,0,0x1200,len(strings),0,0,1,0),
             (names.index(b'.symtab'),2,0,0,0x1300,80,4,1,4,16)]
    for i,h in enumerate(headers): struct.pack_into('<10I',blob,0x1400+i*40,*h)
    prologue=struct.pack('<II',0xe1a00000,0xe12fff1e); blob[0x100:0x108]=prologue
    if candidate:
        struct.pack_into('<I',blob,0x100,0xea0003fe); blob[0x1100:0x1108]=prologue
    return bytes(blob)


def frame(pc,psr=0x60000153):
    regs=list(range(15))+[pc]
    text=f'Trace 0: 0x1234 [00000400/{pc:016x}/00000020/ff020200] \n'
    for i in range(0,16,4): text+=' '.join(f'R{n:02d}={regs[n]:08x}' for n in range(i,i+4))+'\n'
    return text+f'PSR={psr:08x} -ZC- '+('T' if psr&32 else 'A')+' svc32\n'


class RewriteGateTests(unittest.TestCase):
    def check(self,original=None,candidate=None,mapping='f 1000 2000 8'):
        return gate.check_artifacts(image() if original is None else original,image(True) if candidate is None else candidate,mapping,['f'])

    def test_reserved_scoped_artifact(self):
        row=self.check()['rows'][0]
        self.assertEqual(row['input'],0x1000); self.assertFalse(row['thumb'])

    def test_selection_and_exact_map(self):
        for names in ('','f,f','f,','f*'):
            with self.assertRaises(ValueError): gate.selection(names)
        for mapping in ('','f 1000 2000 8\nf 1000 2000 8','f 1000 2000 8\ng 1004 2008 8','f 1001 2000 8','f 1000 100000000 8','f 1000 2000 0','f 1000 2000 ffffffff'):
            with self.subTest(mapping=mapping),self.assertRaises(ValueError): self.check(mapping=mapping)

    def test_no_redirect_or_wrong_branch_cannot_pass(self):
        for branch in (image()[0x100:0x104],struct.pack('<I',0xeb0003fe),struct.pack('<I',0x1a0003fe),struct.pack('<I',0xea0003ff)):
            data=bytearray(image(True)); data[0x100:0x104]=branch
            with self.assertRaises(ValueError): self.check(candidate=bytes(data))

    def test_unreserved_dirty_or_wrong_kernel_boundary_rejected(self):
        for offset,value in ((0x1320+4,0x1000),(0x1320+4,0x2001),(0x1330+4,0x2200),(0x1340+4,0x2000)):
            data=bytearray(image()); struct.pack_into('<I',data,offset,value)
            with self.assertRaises(ValueError): self.check(original=bytes(data))
        data=bytearray(image()); data[0x1100]=1
        with self.assertRaisesRegex(ValueError,'zero-filled'): self.check(original=bytes(data))
        original=bytearray(image()); candidate=bytearray(image(True))
        for data in (original,candidate): struct.pack_into('<I',data,0x1344,0x2104)
        with self.assertRaisesRegex(ValueError,'LOAD boundary'): self.check(original=bytes(original),candidate=bytes(candidate))

    def test_changed_caller_data_load_or_entry_rejected(self):
        for offset in (0x107,0x200,0x18,52+20):
            data=bytearray(image(True)); data[offset]^=1
            with self.assertRaises(ValueError): self.check(candidate=bytes(data))

    def test_wrong_map_or_emitted_prologue_rejected(self):
        for mapping in ('f 1004 2000 8','f 1000 2004 8','f 1000 2000 4'):
            with self.assertRaises(ValueError): self.check(mapping=mapping)
        data=bytearray(image(True)); data[0x1100]^=1
        with self.assertRaisesRegex(ValueError,'prologue'): self.check(candidate=bytes(data))

    def test_live_redirect_pairs_for_arm_and_thumb(self):
        for thumb in (False,True):
            psr=0x60000153|(32 if thumb else 0)
            rows=[dict(name='f',input=0x1000,output=0x2000,thumb=thumb)]
            self.assertEqual(gate.check_execution(frame(0x1000,psr)+frame(0x2000,psr),rows)[0]['pairs'],1)

    def test_missing_reordered_wrong_isa_or_changed_state_rejected(self):
        rows=self.check()['rows']; good=frame(0x1000)+frame(0x2000)
        for text in (frame(0x1000),frame(0x2000),frame(0x2000)+frame(0x1000),good.replace('R00=00000000','R00=00000001',1),good.replace('PSR=60000153','PSR=60000173'),good.replace('0000000000002000','0000000000002004'),good.replace('R15=00002000','R15=00002004')):
            with self.subTest(text=text),self.assertRaises(ValueError): gate.check_execution(text,rows)

    def test_partial_duplicate_registers_privilege_and_cpu_rejected(self):
        good=frame(0x1000)+frame(0x2000)
        for text in ('',good[:-1].rsplit('\n',1)[0],good.replace('R03=','R02='),good.replace('Trace 0:','Trace 1:'),good.replace('svc32','usr32'),good.replace('60000153','60000152'),good+'unknown\n',good.replace('R03=00000003','R03=000000030')):
            with self.assertRaises(ValueError): gate.cpu_frames(text)

    def test_subset_trace_cannot_hide_second_selected_function(self):
        rows=self.check()['rows']+[dict(name='g',input=0x3000,output=0x4000,thumb=False)]
        with self.assertRaisesRegex(ValueError,'pair for g'): gate.check_execution(frame(0x1000)+frame(0x2000),rows)

    def test_bindings_unique_and_reserved_names(self):
        bound=gate.bindings(['instrumented.elf=a.elf'],Path('p.fdata'),Path('o.json'))
        self.assertEqual(set(bound),{'instrumented.elf','optimize.json','profile.fdata','profile.fdata.manifest.json'})
        for rows,profile,record in ((['x=a','x=b'],None,None),(['noequals'],None,None),(['../x=a'],None,None),
                                    (['profile.fdata=a'],Path('p'),None),(['optimize.json=a'],None,Path('o'))):
            with self.subTest(rows=rows),self.assertRaises(ValueError): gate.bindings(rows,profile,record)

    def test_optimizer_record_must_name_input_and_checked_profile(self):
        good=dict(kind='bolt-optimize',input_sha256='i',profile_sha256='p',profile_checked=True)
        gate.check_optimizer_record(good,'i','p')
        for record,profile in ((dict(good,input_sha256='x'),'p'),(dict(good,profile_sha256='x'),'p'),
                               (dict(good,profile_checked=False),'p'),(dict(good,kind='other'),'p'),(good,None)):
            with self.subTest(record=record),self.assertRaises(ValueError): gate.check_optimizer_record(record,'i',profile)


if __name__=='__main__': unittest.main()
