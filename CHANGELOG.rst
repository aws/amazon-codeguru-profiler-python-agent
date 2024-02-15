=========
CHANGELOG
=========

1.2.5 (layer_v12)
===================
* Fix bug which causes agent to crash if line_no was None.

1.2.4 (layer_v11)
===================
* Updated lambda bootstrap code to support profiling python 3.9 lambda functions.

1.2.3 (layer_v10)
===================
* Fix bug to sent agent overhead in the right format: int and as part of memoryInMB (instead of the previous string as part of memory_usage_mb).

1.2.2 (layer_v9)
===================
* Fix bug on calculating active millis since start.

1.2.1 (layer_v8)
===================
* Fix bug for module path for Fargate.

1.2.0 (layer_v7)
===================
* Add operation name frame in stacks with boto api calls.
* Adds NUM_TIMES_SAMPLED agent metadata to the submitted profile.
* Add errors metadata in agent debug info with granular sdk client error metrics.
* Add create_profiling_group call in refresh_configuration and report().

1.0.6 (layer_v5)
===================
* Use IMDSv2 instead of v1 when calling EC2 Instance Metadata.

1.0.5 (layer_v5)
===================
* Improve CPU usage checker and ProfilerDisabler (Issue #19)

1.0.4 (layer_v4)
===================
* Attempt to report profile before sample to avoid incorrect profile end time (Issue #15)
* Add synthetic frame for lxml schema init

1.0.3
===================
* Add requirements.txt in PyPI source release (Issue #13)

1.0.2
===================
* Fix timestamp bug in file reporter (Issue #10)

1.0.1 (layer_v3)
===================
* Fix bug for running agent in Windows; Update module_path_extractor to support Windows applications
* Use json library instead of custom encoder for profile encoding for more reliable performance
* Specify min version for boto3 in setup.py

1.0.0 (layer_v1, layer_v2)
==========================
* Initial Release
