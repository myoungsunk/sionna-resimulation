# P4 gate

verdict: **WITHIN_SCENE_IMPROVEMENT_GENERALIZATION_NOT_VERIFIED**

```json
{
 "prediction_file_sha256_written_before_truth": "2e4351bdf5d8f16c0783c637e8b6584a225e226efa3135ab5ccc6d25c852ef1a",
 "chosen_model": "E1_on_B",
 "levels": {
  "a_LORO_exploratory": "P1/P3",
  "b_site_disjoint_new_XY": "this test",
  "c_other_scene": "NOT_AVAILABLE -> GENERALIZATION_NOT_VERIFIED"
 },
 "gate_noise_free_full": {
  "point_change": -0.17150599687825407,
  "ci95": [
   -0.2250522830483489,
   -0.13679366954522093
  ],
  "needs": "point <= -10% and CI upper < 0",
  "within_scene_pass": true
 },
 "verdict": "WITHIN_SCENE_IMPROVEMENT_GENERALIZATION_NOT_VERIFIED"
}
```
