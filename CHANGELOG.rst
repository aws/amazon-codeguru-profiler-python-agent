=========
CHANGELOG
=========

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
