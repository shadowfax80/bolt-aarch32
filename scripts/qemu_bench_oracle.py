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


def check_results(image_sha256,actual,platform='qemu-virt'):
    contract=check_contract(image_sha256,platform)
    expected=reference_results()
    if actual!=expected:
        wrong=[name for name,value in expected.items() if actual.get(name)!=value]
        raise ValueError('independent workload oracle mismatch: '+','.join(wrong or ['unexpected workload']))
    return {'input_sha256':image_sha256,'contract':contract,
            'expected':expected,'matched_workloads':len(expected),
            'scope':'independent sink arithmetic for approved input; not execution/state, PMU or clean-build proof'}
