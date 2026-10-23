Third-party code shipped with the plugin so it runs without installing anything.

| package | version | license | source |
|---|---|---|---|
| `yaml/` (PyYAML, pure-Python part) | 6.0.3 | MIT, see `yaml/LICENSE` | https://github.com/yaml/pyyaml |

The plugin's launcher (`scripts/skillbom`) puts this folder on `PYTHONPATH`. The optional LibYAML C extension is not included; PyYAML falls back to its pure-Python implementation.
