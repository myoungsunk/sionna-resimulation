# P1 decision

result: **KEEP_B_OLD_AND_GO_TO_P2**

```json
{
 "fits": {
  "R2": {
   "const": -0.537050788454153,
   "intercept": -0.5412388708371483,
   "slope": 1.0006766984948787
  },
  "R4": {
   "const": -0.5367756495820671,
   "intercept": -0.5382530280710546,
   "slope": 1.0002340130335532
  },
  "R5": {
   "const": -0.5340445440661892,
   "intercept": -0.5367873523198352,
   "slope": 1.0004378840096821
  }
 },
 "plan_reference_pose_pooled": {
  "B_old": 0.143847,
  "C_const": 0.145249,
  "C2_affine": 0.144594
 },
 "recomputed_pose_pooled": {
  "A_raw": 0.5023262508246334,
  "B_old": 0.14384691454192222,
  "C_const": 0.1452494394571537,
  "C2_affine": 0.14459400141049605
 },
 "relative_change_vs_B_site_cluster_bootstrap": {
  "C_const": {
   "point": 0.00975012164631961,
   "ci95": [
    0.006965157528572274,
    0.012719517503883032
   ]
  },
  "C2_affine": {
   "point": 0.005193624562285004,
   "ci95": [
    0.003616853869169795,
    0.007087062280363893
   ]
  }
 },
 "n_site_clusters": 2815,
 "limitations": [
  "3 routes, 1 scene: route hold-out is exploratory, not independent geometry",
  "pose counts weight clusters",
  "1 XY (route start) shared by R2 and R4 is still in the exploratory LORO"
 ],
 "decision": "KEEP_B_OLD_AND_GO_TO_P2"
}
```
