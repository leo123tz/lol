import numpy as np,sys
S=sys.argv[1]
a=np.fromfile(f"{S}/data/game.raw",np.uint8).reshape(-1,324,576,3).astype(np.float32).mean(-1)
W=a[:,60:280,120:300]; R=a[:,70:260,280:440]
for nm,x in (("walk",W),("run",R)):
    d=np.array([np.abs(x[i]-x[i+1]).mean() for i in range(len(x)-1)])
    print(nm,"consecutive diff (first 70):",np.round(d[:70],1).tolist())
    for P in (29,30,31,19,20,21,59,60,61):
        print(nm,P,round(float(np.mean([np.abs(x[i]-x[i+P]).mean() for i in range(0,len(x)-P)])),2))
