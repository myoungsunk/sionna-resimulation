# E0-A2 control input recovery investigation

These are unchanged copies of the pre-A2 control-only investigation. Original scratch paths inside the files are historical provenance strings. `PATH_MAP_AND_HASHES.json` maps each packaged file to its repository location and verifies its copied bytes. No scientific filter replay occurred in this investigation.

The LFS lookup receipt records HTTP 200 with four object-level 404 results, request ID `4839:281BEF:67DF9E:7C3730:6AEC0B56`, and the exact requested original NPZ OIDs. It does not assert that private Windows caches or unexamined archives are absent.

The diagnostic code is a record of a bounded recovery attempt. It is not the A2 materializer and must not be used to choose a runtime or control values after observing a replay. A2 uses one separately frozen primary runtime and the unmodified original control recipe.

The archived-state inverse diagnostic is evidence about approximate consistency only; it is not an input to A2 control generation and does not establish byte identity or full recursive reproduction.
