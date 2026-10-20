# Full-only observable RF indicators: executed descriptive audit

{
  "status": "EXECUTED_FULL_ONLY_FEATURE_DESCRIPTIVE_AUDIT",
  "n_observed_packets": 2647,
  "n_routes": 6,
  "n_anchors_routes": 9,
  "n_preselected_events": 12,
  "n_positive_skip_events": 7,
  "online_input": [
    "two time-aligned port CIR powers from current Full packet"
  ],
  "excluded_predictors": [
    "H_LoS",
    "H_Full-H_LoS",
    "true_pose",
    "true_heading",
    "true_arrival",
    "future_packets",
    "coherent_cross_port_phase"
  ],
  "feature_windows_ns": [
    4,
    16,
    40
  ],
  "offline_use": [
    "known geometry episode identity",
    "historical causal RF skip effects",
    "Direct-LoS and geometric arrival timing diagnostics"
  ],
  "new_EKF_runs": 0,
  "online_gate_or_model_selected": false,
  "independent_event_or_environment_validation": false,
  "hardware_replay": false,
  "notes": [
    "Raw H ideal simulation; hardware noise and sequential port synchronization not emulated",
    "Measured |s| saturation is not Heading Jacobian",
    "No current-prior covariance or likelihood-branch metrics computed in this artifact",
    "Scalar AUROC is 12 selected correlated events, not validation",
    "R4/R5 old or regenerated Mount45 excluded from this new six-route audit",
    "Time oversampling compares grid only, no repeated CIR acquisition"
  ],
  "pure_path_qa": {
    "phase_independent_per_port": "PASS",
    "common_gain_invariance": "PASS",
    "single_path_constant_port_ratio": "PASS",
    "synthetic_single_path_leading_edge_bias": [
      {
        "factor": 4,
        "tap_spacing_ns": 0.49885263893045995,
        "detected_minus_geom_ns": -2.2667155542252786
      },
      {
        "factor": 8,
        "tap_spacing_ns": 0.24942631946522997,
        "detected_minus_geom_ns": -2.5161418736905077
      },
      {
        "factor": 16,
        "tap_spacing_ns": 0.12471315973261499,
        "detected_minus_geom_ns": -2.5161418736905077
      },
      {
        "factor": 32,
        "tap_spacing_ns": 0.06235657986630749,
        "detected_minus_geom_ns": -2.5161418736905077
      },
      {
        "factor": 64,
        "tap_spacing_ns": 0.031178289933153747,
        "detected_minus_geom_ns": -2.547320163623663
      }
    ],
    "is_hardware_test": false
  }
}

## Event metrics (candidate features only)
|event|skip gain deg|Dpol4|sigma_pol16|late E40|detector Ds|abs s|
|--|--:|--:|--:|--:|--:|--:|
|C01 A [16,21) V1|+5.393|0.3178|0.3653|0.4568|0.1009|0.5223|
|C01 A [10,16) V1|-3.079|0.2206|0.3127|0.2719|0.0650|0.1030|
|C01 B [16,21) V1|+4.340|0.1594|0.2977|0.2889|0.0824|0.5863|
|C02 A [4,10) V1|+1.775|0.1836|0.2051|0.1038|0.0635|0.1229|
|C03 A [1,4) V1|+0.767|0.0344|0.1244|0.0508|0.0057|0.1189|
|C03 A [4,10) V1|-3.115|0.0804|0.1992|0.1970|0.0158|0.0982|
|C03 B [10,16) V1|+0.610|0.0490|0.1702|0.0844|0.0087|0.3206|
|C03 B [10,16) V2|+0.537|0.0490|0.1702|0.0844|0.0087|0.3206|
|O02 O0 [4,8) V1|-4.330|0.0830|0.1475|0.1662|0.0595|0.1048|
|O03 O0 [4,8) V1|+1.798|0.2161|0.3344|0.6143|0.0476|0.5623|
|O03 O0 [4,8) V2|-15.347|0.1606|0.3294|0.5389|0.0355|0.5403|
|O03 O0 [0,4) V2|-14.462|0.1357|0.2323|0.2068|0.0400|0.3757|

## All12 single-feature rankings (no policy fitting)
{"scope": "all12", "feature": "pol_fp_vs_early4_abs_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.45714285714285713, "spearman_gain": 0.2867132867132868, "new_policy_trained": false}
{"scope": "all12", "feature": "pol_delay_std16_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.4857142857142857, "spearman_gain": 0.25874125874125875, "new_policy_trained": false}
{"scope": "all12", "feature": "pol_early4_vs16_abs_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.37142857142857144, "spearman_gain": 0.04895104895104895, "new_policy_trained": false}
{"scope": "all12", "feature": "late_energy_fraction40_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.37142857142857144, "spearman_gain": 0.08391608391608392, "new_policy_trained": false}
{"scope": "all12", "feature": "delay_spread40_ns_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.42857142857142855, "spearman_gain": 0.27272727272727276, "new_policy_trained": false}
{"scope": "all12", "feature": "peak_minus_detected_fp_ns_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.5, "spearman_gain": 0.11826247919781652, "new_policy_trained": false}
{"scope": "all12", "feature": "port_envelope_mismatch16_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.4857142857142857, "spearman_gain": 0.26970269031026334, "new_policy_trained": false}
{"scope": "all12", "feature": "detector_time_span_ns_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.4142857142857143, "spearman_gain": 0.17986992238752703, "new_policy_trained": false}
{"scope": "all12", "feature": "detector_pol_span_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.4857142857142857, "spearman_gain": 0.39860139860139865, "new_policy_trained": false}
{"scope": "all12", "feature": "abs_s_full_median", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.7428571428571429, "spearman_gain": 0.3706293706293707, "new_policy_trained": false}
{"scope": "all12", "feature": "saturation_full_mean", "n": 12, "skip_benefit_positive": 7, "AUC_high_is_suspect": 0.7, "spearman_gain": 0.2094281257618944, "new_policy_trained": false}

## Fixed physical-reference firstpath checks (ns, no antenna/calibration offset removed)
{"route": "C01", "anchor": "A", "low": "16", "high": "21", "visit": "1", "n": "51", "t_start_s": "70.0", "t_end_s": "82.5", "n_direct_valid": "51", "full_minus_los_4_rms_ns": "0.644015987596431", "full_minus_los_4_mean_ns": "0.5771040332724928", "full_minus_geom_4_rms_ns": "1.2405897363175724", "full_minus_geom_4_mean_ns": "-1.2072097443261782", "los_minus_geom_4_rms_ns": "1.7843137775986693", "los_minus_geom_4_mean_ns": "-1.784313777598669", "delta_s_4_rms": "0.5061468011568755", "full_minus_los_16_rms_ns": "0.6014084684427016", "full_minus_los_16_mean_ns": "0.5281969118087223", "full_minus_geom_16_rms_ns": "1.4297598582367221", "full_minus_geom_16_mean_ns": "-1.407728942327637", "los_minus_geom_16_rms_ns": "1.9370776490352222", "los_minus_geom_16_mean_ns": "-1.9359258541363642", "delta_s_16_rms": "0.523025167114159", "scope": ""}
{"route": "C01", "anchor": "A", "low": "10", "high": "16", "visit": "1", "n": "30", "t_start_s": "40.0", "t_end_s": "69.0", "n_direct_valid": "30", "full_minus_los_4_rms_ns": "0.6754496661541753", "full_minus_los_4_mean_ns": "0.5487379028235059", "full_minus_geom_4_rms_ns": "1.3149820121355706", "full_minus_geom_4_mean_ns": "-1.2483515606331907", "los_minus_geom_4_rms_ns": "1.8029768007283742", "los_minus_geom_4_mean_ns": "-1.797089463456697", "delta_s_4_rms": "0.18909840547251958", "full_minus_los_16_rms_ns": "0.708051573628797", "full_minus_los_16_mean_ns": "0.5861518507432902", "full_minus_geom_16_rms_ns": "1.4465802743343708", "full_minus_geom_16_mean_ns": "-1.3896931416634881", "los_minus_geom_16_rms_ns": "1.9761610197111472", "los_minus_geom_16_mean_ns": "-1.9758449924067785", "delta_s_16_rms": "0.16842752039489442", "scope": ""}
{"route": "C01", "anchor": "B", "low": "16", "high": "21", "visit": "1", "n": "51", "t_start_s": "70.0", "t_end_s": "82.5", "n_direct_valid": "51", "full_minus_los_4_rms_ns": "0.567491229167436", "full_minus_los_4_mean_ns": "0.5477597603942304", "full_minus_geom_4_rms_ns": "1.3221431193633861", "full_minus_geom_4_mean_ns": "-1.313794842433598", "los_minus_geom_4_rms_ns": "1.8615546028278267", "los_minus_geom_4_mean_ns": "-1.8615546028278265", "delta_s_4_rms": "0.16108909125817766", "full_minus_los_16_rms_ns": "0.5585538008621289", "full_minus_los_16_mean_ns": "0.5502051164674191", "full_minus_geom_16_rms_ns": "1.427338355924412", "full_minus_geom_16_mean_ns": "-1.4238358657270818", "los_minus_geom_16_rms_ns": "1.9750070608224612", "los_minus_geom_16_mean_ns": "-1.974040982194502", "delta_s_16_rms": "0.13786478896084997", "scope": ""}
{"route": "C02", "anchor": "A", "low": "4", "high": "10", "visit": "1", "n": "30", "t_start_s": "8.0", "t_end_s": "37.0", "n_direct_valid": "30", "full_minus_los_4_rms_ns": "0.27323284321319274", "full_minus_los_4_mean_ns": "0.11639894908377399", "full_minus_geom_4_rms_ns": "1.683535182529277", "full_minus_geom_4_mean_ns": "-1.6701457675018294", "los_minus_geom_4_rms_ns": "1.7915170537672769", "los_minus_geom_4_mean_ns": "-1.7865447165856034", "delta_s_4_rms": "0.11105846318495335", "full_minus_los_16_rms_ns": "0.24204208034869198", "full_minus_los_16_mean_ns": "0.13718447570587647", "full_minus_geom_16_rms_ns": "1.8500977934589649", "full_minus_geom_16_mean_ns": "-1.84058708580307", "los_minus_geom_16_rms_ns": "1.978329402651406", "los_minus_geom_16_mean_ns": "-1.9777715615089464", "delta_s_16_rms": "0.10033708434287718", "scope": ""}
{"route": "C03", "anchor": "A", "low": "1", "high": "4", "visit": "1", "n": "15", "t_start_s": "0.0", "t_end_s": "5.0", "n_direct_valid": "15", "full_minus_los_4_rms_ns": "0.0", "full_minus_los_4_mean_ns": "0.0", "full_minus_geom_4_rms_ns": "1.5903930264087796", "full_minus_geom_4_mean_ns": "-1.585911959441995", "los_minus_geom_4_rms_ns": "1.5903930264087796", "los_minus_geom_4_mean_ns": "-1.585911959441995", "delta_s_4_rms": "0.01087078833119187", "full_minus_los_16_rms_ns": "0.0", "full_minus_los_16_mean_ns": "0.0", "full_minus_geom_16_rms_ns": "1.918559137669719", "full_minus_geom_16_mean_ns": "-1.918480385395635", "los_minus_geom_16_rms_ns": "1.918559137669719", "los_minus_geom_16_mean_ns": "-1.918480385395635", "delta_s_16_rms": "0.013379439658397406", "scope": ""}
{"route": "C03", "anchor": "A", "low": "4", "high": "10", "visit": "1", "n": "30", "t_start_s": "6.0", "t_end_s": "35.0", "n_direct_valid": "30", "full_minus_los_4_rms_ns": "0.27323284321319274", "full_minus_los_4_mean_ns": "0.08314210648840999", "full_minus_geom_4_rms_ns": "1.7128210952159078", "full_minus_geom_4_mean_ns": "-1.6922928475123886", "los_minus_geom_4_rms_ns": "1.7809538745588942", "los_minus_geom_4_mean_ns": "-1.7754349540007983", "delta_s_4_rms": "0.06966322675671008", "full_minus_los_16_rms_ns": "0.22192869425386844", "full_minus_los_16_mean_ns": "0.07898500116398949", "full_minus_geom_16_rms_ns": "1.9072824934844492", "full_minus_geom_16_mean_ns": "-1.8959910084089933", "los_minus_geom_16_rms_ns": "1.975402310844954", "los_minus_geom_16_mean_ns": "-1.9749760095729827", "delta_s_16_rms": "0.06376657363984842", "scope": ""}
{"route": "C03", "anchor": "B", "low": "10", "high": "16", "visit": "1", "n": "78", "t_start_s": "36.0", "t_end_s": "66.0", "n_direct_valid": "78", "full_minus_los_4_rms_ns": "0.0798803520927303", "full_minus_los_4_mean_ns": "0.01279109330590923", "full_minus_geom_4_rms_ns": "1.8810455518655287", "full_minus_geom_4_mean_ns": "-1.8796144590368489", "los_minus_geom_4_rms_ns": "1.8932953698845785", "los_minus_geom_4_mean_ns": "-1.892405552342758", "delta_s_4_rms": "0.021852936660340015", "full_minus_los_16_rms_ns": "0.034589207087774944", "full_minus_los_16_mean_ns": "0.009593319979431922", "full_minus_geom_16_rms_ns": "1.9953149043432175", "full_minus_geom_16_mean_ns": "-1.9947342987900316", "los_minus_geom_16_rms_ns": "2.004824465410625", "los_minus_geom_16_mean_ns": "-2.004327618769464", "delta_s_16_rms": "0.02038209835617877", "scope": ""}
{"route": "C03", "anchor": "B", "low": "10", "high": "16", "visit": "2", "n": "78", "t_start_s": "147.0", "t_end_s": "177.0", "n_direct_valid": "78", "full_minus_los_4_rms_ns": "0.0798803520927303", "full_minus_los_4_mean_ns": "0.01279109330590923", "full_minus_geom_4_rms_ns": "1.8810455518655287", "full_minus_geom_4_mean_ns": "-1.8796144590368489", "los_minus_geom_4_rms_ns": "1.8932953698845785", "los_minus_geom_4_mean_ns": "-1.892405552342758", "delta_s_4_rms": "0.021852936641531855", "full_minus_los_16_rms_ns": "0.034589207087774944", "full_minus_los_16_mean_ns": "0.009593319979431922", "full_minus_geom_16_rms_ns": "1.9953149043432175", "full_minus_geom_16_mean_ns": "-1.9947342987900316", "los_minus_geom_16_rms_ns": "2.004824465410625", "los_minus_geom_16_mean_ns": "-2.004327618769464", "delta_s_16_rms": "0.020382098350869186", "scope": ""}
{"route": "O02", "anchor": "O0", "low": "4", "high": "8", "visit": "1", "n": "20", "t_start_s": "17.0", "t_end_s": "36.0", "n_direct_valid": "20", "full_minus_los_4_rms_ns": "0.15775105558058364", "full_minus_los_4_mean_ns": "0.049885263893046", "full_minus_geom_4_rms_ns": "1.6242085371682138", "full_minus_geom_4_mean_ns": "-1.6188536206710478", "los_minus_geom_4_rms_ns": "1.6729414199297663", "los_minus_geom_4_mean_ns": "-1.6687388845640936", "delta_s_4_rms": "0.1807637886120923", "full_minus_los_16_rms_ns": "0.15017453081403143", "full_minus_los_16_mean_ns": "0.10600618577272274", "full_minus_geom_16_rms_ns": "1.7645787731328122", "full_minus_geom_16_mean_ns": "-1.7622737543635547", "los_minus_geom_16_rms_ns": "1.868643669929391", "los_minus_geom_16_mean_ns": "-1.868279940136278", "delta_s_16_rms": "0.1865784380217412", "scope": ""}
{"route": "O03", "anchor": "O0", "low": "4", "high": "8", "visit": "1", "n": "20", "t_start_s": "17.0", "t_end_s": "36.0", "n_direct_valid": "2", "full_minus_los_4_rms_ns": "0.35274208380053257", "full_minus_los_4_mean_ns": "-0.24942631946522997", "full_minus_geom_4_rms_ns": "2.096502444989755", "full_minus_geom_4_mean_ns": "-2.09269308278958", "los_minus_geom_4_rms_ns": "1.8473727675219807", "los_minus_geom_4_mean_ns": "-1.8432667633243511", "delta_s_4_rms": "0.18677002236673895", "full_minus_los_16_rms_ns": "0.08818552095013314", "full_minus_los_16_mean_ns": "-0.06235657986630749", "full_minus_geom_16_rms_ns": "2.155998860627315", "full_minus_geom_16_mean_ns": "-2.1550496626558875", "los_minus_geom_16_rms_ns": "2.0926937040078255", "los_minus_geom_16_mean_ns": "-2.09269308278958", "delta_s_16_rms": "0.17992591803077743", "scope": ""}
{"route": "O03", "anchor": "O0", "low": "4", "high": "8", "visit": "2", "n": "20", "t_start_s": "82.0", "t_end_s": "101.0", "n_direct_valid": "3", "full_minus_los_4_rms_ns": "0.2880127053724562", "full_minus_los_4_mean_ns": "-0.16628421297681997", "full_minus_geom_4_rms_ns": "1.9340897617711514", "full_minus_geom_4_mean_ns": "-1.9308073555890992", "los_minus_geom_4_rms_ns": "1.768776034667747", "los_minus_geom_4_mean_ns": "-1.7645231426122798", "delta_s_4_rms": "0.15690809554950283", "full_minus_los_16_rms_ns": "0.2160095290293422", "full_minus_los_16_mean_ns": "-0.207855266221025", "full_minus_geom_16_rms_ns": "2.181025621627521", "full_minus_geom_16_mean_ns": "-2.1802336750543283", "los_minus_geom_16_rms_ns": "1.9723863259982735", "los_minus_geom_16_mean_ns": "-1.972378408833304", "delta_s_16_rms": "0.15206270057906468", "scope": ""}
{"route": "O03", "anchor": "O0", "low": "0", "high": "4", "visit": "2", "n": "130", "t_start_s": "102.0", "t_end_s": "191.0", "n_direct_valid": "130", "full_minus_los_4_rms_ns": "0.23561318863550373", "full_minus_los_4_mean_ns": "0.09593319979431922", "full_minus_geom_4_rms_ns": "1.7423732110875094", "full_minus_geom_4_mean_ns": "-1.7296457207150226", "los_minus_geom_4_rms_ns": "1.8311863707008635", "los_minus_geom_4_mean_ns": "-1.825578920509342", "delta_s_4_rms": "0.07840605871754623", "full_minus_los_16_rms_ns": "0.13485355521382036", "full_minus_los_16_mean_ns": "0.05372259188481876", "full_minus_geom_16_rms_ns": "1.918400825343995", "full_minus_geom_16_mean_ns": "-1.913837464320116", "los_minus_geom_16_rms_ns": "1.9687700830250703", "los_minus_geom_16_mean_ns": "-1.9675600562049345", "delta_s_16_rms": "0.06870394502965556", "scope": ""}
