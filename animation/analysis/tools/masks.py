import numpy as np,sys
from PIL import Image
from scipy import ndimage as ndi
S=sys.argv[1]
f=np.load(f"{S}/data/frames.npy").astype(np.float32); n=len(f)
r,g,b=f[...,0],f[...,1],f[...,2]
br=(r+g+b)/3; ratio=(b-r)/np.maximum(br,1)
# temporal-mode background plate: largest cluster of mutually-close colours over time
H_,W_=f.shape[1:3]
best_cnt=np.zeros((H_,W_),np.int32); plate=np.zeros((H_,W_,3),np.float32)
for i in range(n):
    d=np.sqrt(((f-f[i][None])**2).sum(-1))  # n,H,W
    close=d<12; cnt=close.sum(0)
    upd=cnt>best_cnt
    mean=(f*close[...,None]).sum(0)/np.maximum(cnt,1)[...,None]
    plate[upd]=mean[upd]; best_cnt[upd]=cnt[upd]
pbr=plate.mean(-1); pra=(plate[...,2]-plate[...,0])/np.maximum(pbr,1)
W=(ratio<0.27)&(br>112)
often_white=ndi.binary_dilation(W.mean(0)>0.3,iterations=10)
plate_is_char=((pra<0.27)&(pbr>112))|often_white|(pbr<50)
rowground=np.median(plate[:, list(range(0,90))+list(range(480,576))],axis=1)  # side columns are pure ground
ground_like=np.sqrt(((plate-rowground[:,None,:])**2).sum(-1))<22
valid=(best_cnt>=7)&~plate_is_char&ground_like
dist=np.sqrt(((f-plate[None])**2).sum(-1))
shadow=(br<64)&(ratio>0.33); shadow[:, :185]=False  # cast shadows lie on the floor below the hips
BG=((valid[None]&(dist<13))|shadow)&~W
T=(ratio<0.30)&(br<=112)&(br>=50)&~BG
def keep_main(w):
    lb,m=ndi.label(w)
    if m==0: return w
    sz=ndi.sum(w,lb,range(1,m+1)); big=np.isin(lb,1+np.where(sz>250)[0]); near=ndi.binary_dilation(big,iterations=12)
    return np.isin(lb,[i+1 for i in range(m) if sz[i]>250 or near[lb==i+1].any()])
L=[];BS=[]
for k in range(n):
    w=ndi.binary_opening(W[k],iterations=1); w=ndi.binary_closing(w,iterations=1); w[:80]=False; w=keep_main(w)
    t=ndi.binary_opening(T[k],iterations=2)&ndi.binary_dilation(w,iterations=20)&~w
    bs=ndi.binary_opening(BG[k],iterations=1)&~ndi.binary_dilation(w,iterations=8)&~t  # shaded faces next to lit ones look like ground
    lab=np.zeros(w.shape,np.uint8); lab[t]=1; lab[w]=2; L.append(lab); BS.append(bs)
L=np.array(L); BS=np.array(BS)
np.save(f"{S}/data/labels.npy",L); np.save(f"{S}/data/bgsure.npy",BS)
print("valid plate frac (rows 80-280):", valid[80:280].mean().round(3), " BG frac:", BS[:,80:280].mean().round(3))
tiles=[]
for k in range(0,24,3):
    im=f[k].copy(); unk=~BS[k]&(L[k]==0)
    im[BS[k]]=im[BS[k]]*0.4+np.array([0,0,255])*0.6
    im[L[k]==2]=im[L[k]==2]*0.5+np.array([0,255,0])*0.5
    im[L[k]==1]=im[L[k]==1]*0.5+np.array([255,0,0])*0.5
    tiles.append(im.astype(np.uint8)[80:290,100:460])
Image.fromarray(np.concatenate([np.concatenate(tiles[:4],1),np.concatenate(tiles[4:],1)],0)).save(f"{S}/sheets/masks5.png")
# face features (eyes + mouth): dark pixels enclosed by the white head
FACE=[]
for k in range(n):
    wr=W[k].copy(); wr[180:]=False; wr[:80]=False
    enclosed=ndi.binary_fill_holes(ndi.binary_closing(wr,iterations=2))&~ndi.binary_erosion(wr,iterations=0)
    fc=enclosed&(br[k]<95)&~wr
    lb,m=ndi.label(fc)
    if m:
        sz=ndi.sum(fc,lb,range(1,m+1)); fc=np.isin(lb,1+np.where((sz>=3)&(sz<=120))[0])
    FACE.append(fc)
FACE=np.array(FACE); np.save(f"{S}/data/face.npy",FACE)
tiles=[]
for k in range(0,24,4):
    im=f[k,85:150,170:420].copy(); im[FACE[k,85:150,170:420]]=[255,0,0]; tiles.append(im.astype(np.uint8))
Image.fromarray(np.concatenate(tiles,0)).resize((750,1170),Image.NEAREST).save(f"{S}/sheets/face.png")
print("face px per frame:", FACE[:,:,:300].sum((1,2)).tolist()[:8], FACE[:,:,300:].sum((1,2)).tolist()[:8])
