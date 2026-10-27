from pathlib import Path
R=Path(__file__).resolve().parent
src=Path(r'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2\research\FFD_P0P3_20261016\source_model.py').read_text()
def replace(a,b):
 global src
 assert src.count(a)==1,a
 src=src.replace(a,b)
replace('class SourceFFD:', 'class GeometryFFD:')
replace('  dr=np.column_stack([u/dist,v/dist,np.zeros(n)])','''  dr=np.column_stack([u/dist,v/dist,np.zeros(n)])
  real_dist=dist.copy();real_dr=dr.copy()
  D=np.zeros((n,3,3));D[:,:,0]=(np.array([1,0,0])[None]-d*dr[:,0,None])/dist[:,None];D[:,:,1]=(np.array([0,1,0])[None]-d*dr[:,1,None])/dist[:,None]
  d,dist,dr,D=self.geometry(x,case,d,dist,dr,D)''')
replace("   D=np.zeros((n,3,3));D[:,:,0]=(np.array([1,0,0])[None]-d*dr[:,0,None])/dist[:,None];D[:,:,1]=(np.array([0,1,0])[None]-d*dr[:,1,None])/dist[:,None]\n",'')
replace('return h,dh,dist,dr,np.column_stack([cell_t,*cells]),rho','return h,dh,real_dist,real_dr,np.column_stack([cell_t,*cells]),rho')
src+='''
 def geometry(self,x,case,d,dist,dr,D):
  # d is anchor-to-tag; both antennas consume this same vector.
  if getattr(self,'explicit',None) is not None:
   uu,rr=self.explicit
   return -np.broadcast_to(uu,d.shape).copy(),np.broadcast_to(rr,dist.shape).copy(),dr,D
  modes=getattr(self,'modes',None)
  if modes is None:return d,dist,dr,D
  modes=np.broadcast_to(np.asarray(modes),len(x));gt=np.broadcast_to(self.gt,(len(x),4))
  a=np.asarray(case['anchor']);height=a[2]-case['robot_z_m']
  vx=x[:,0]-a[0];vy=x[:,1]-a[1];rho=np.hypot(vx,vy)
  assert np.all(rho>1e-9),'undefined azimuth axis'
  beta=np.arctan2(-vy,-vx);el=np.arctan2(height,rho)
  gx=gt[:,0]-a[0];gy=gt[:,1]-a[1];grho=np.hypot(gx,gy)
  gb=np.arctan2(-gy,-gx);ge=np.arctan2(height,grho)
  az=(modes=='CUT_ALL')|(modes=='CUT_AZ');ee=(modes=='CUT_ALL')|(modes=='CUT_EL');rr=(modes=='CUT_ALL')|(modes=='CUT_R')
  beta=np.where(az,gb,beta);el=np.where(ee,ge,el)
  cb,sb,ce,se=np.cos(beta),np.sin(beta),np.cos(el),np.sin(el)
  changed=az|ee
  dnew=-np.column_stack([ce*cb,ce*sb,se])
  db=np.column_stack([-vy/rho**2,vx/rho**2,np.zeros(len(x))]);db[az]=0
  de=np.column_stack([-height*vx/(rho*dist**2),-height*vy/(rho*dist**2),np.zeros(len(x))]);de[ee]=0
  dd_db=np.column_stack([ce*sb,-ce*cb,np.zeros(len(x))])
  dd_de=np.column_stack([se*cb,se*sb,-ce])
  deriv=dd_db[:,:,None]*db[:,None,:]+dd_de[:,:,None]*de[:,None,:]
  d[changed]=dnew[changed];D[changed]=deriv[changed]
  dist[rr]=np.sqrt(grho[rr]**2+height**2);dr[rr]=0
  return d,dist,dr,D
'''
(R/'geometry_model.py').write_text(src,encoding='utf-8')
print('Generated auditable physical-geometry model')
