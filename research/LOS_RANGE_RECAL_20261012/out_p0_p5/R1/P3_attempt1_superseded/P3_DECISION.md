# P3 decision

chosen for P4: **D1+E1**

```json
{
 "verdicts": {
  "C_const": {
   "rel_to_B_site_weighted": 1.008594652400251,
   "better_in_all_folds": false,
   "carried_to_P4": false
  },
  "C2_affine": {
   "rel_to_B_site_weighted": 1.0046919324125945,
   "better_in_all_folds": false,
   "carried_to_P4": false
  },
  "D1_fractional": {
   "rel_to_B_site_weighted": 0.9667949206027731,
   "better_in_all_folds": true,
   "carried_to_P4": false
  },
  "E1_on_B": {
   "rel_to_B_site_weighted": 0.8373535123594549,
   "better_in_all_folds": true,
   "carried_to_P4": true
  },
  "D1+E1": {
   "rel_to_B_site_weighted": 0.8230572099430894,
   "better_in_all_folds": true,
   "carried_to_P4": true
  },
  "D2_template": {
   "rel_to_B_site_weighted": 0.9662640380951658,
   "better_in_all_folds": true,
   "carried_to_P4": false
  }
 },
 "pooled_full": [
  {
   "arm": "B_old",
   "rmse_site": 0.15239776702025665,
   "rmse_pose": 0.143863177122897,
   "abs_p95_mean": 0.2203887165329815,
   "per_fold_rmse_site": {
    "R2": 0.11817,
    "R4": 0.21137,
    "R5": 0.13833
   }
  },
  {
   "arm": "C_const",
   "rmse_site": 0.15370757285437017,
   "rmse_pose": 0.14526433632470243,
   "abs_p95_mean": 0.22450247072774246,
   "per_fold_rmse_site": {
    "R2": 0.1205,
    "R4": 0.21259,
    "R5": 0.13919
   }
  },
  {
   "arm": "C2_affine",
   "rmse_site": 0.15311280704294603,
   "rmse_pose": 0.14460876598410644,
   "abs_p95_mean": 0.22305889891415331,
   "per_fold_rmse_site": {
    "R2": 0.11941,
    "R4": 0.21234,
    "R5": 0.13859
   }
  },
  {
   "arm": "D1_fractional",
   "rmse_site": 0.14733738706638894,
   "rmse_pose": 0.1381556261598027,
   "abs_p95_mean": 0.210005331932739,
   "per_fold_rmse_site": {
    "R2": 0.11069,
    "R4": 0.20913,
    "R5": 0.13219
   }
  },
  {
   "arm": "E1_on_B",
   "rmse_site": 0.1276108054901498,
   "rmse_pose": 0.11782957230343215,
   "abs_p95_mean": 0.1815099976052783,
   "per_fold_rmse_site": {
    "R2": 0.08413,
    "R4": 0.19411,
    "R5": 0.11039
   }
  },
  {
   "arm": "D1+E1",
   "rmse_site": 0.1254320809252494,
   "rmse_pose": 0.1153980193785293,
   "abs_p95_mean": 0.17002479885257848,
   "per_fold_rmse_site": {
    "R2": 0.08135,
    "R4": 0.19293,
    "R5": 0.10736
   }
  },
  {
   "arm": "D2_template",
   "rmse_site": 0.14725648175767947,
   "rmse_pose": 0.1405963459101818,
   "abs_p95_mean": 0.23394730972375008,
   "per_fold_rmse_site": {
    "R2": 0.11176,
    "R4": 0.21014,
    "R5": 0.13057
   }
  }
 ],
 "pooled_los": [
  {
   "arm": "B_old",
   "rmse_site": 0.04686870266828066,
   "rmse_pose": 0.04654987575659577
  },
  {
   "arm": "C_const",
   "rmse_site": 0.04671729461799499,
   "rmse_pose": 0.04642578051329268
  },
  {
   "arm": "C2_affine",
   "rmse_site": 0.04674091938152991,
   "rmse_pose": 0.046400247348656824
  },
  {
   "arm": "D1_fractional",
   "rmse_site": 0.016170564355796415,
   "rmse_pose": 0.016636081903672367
  },
  {
   "arm": "D2_template",
   "rmse_site": 0.021548812029250863,
   "rmse_pose": 0.02168673390190711
  }
 ]
}
```
