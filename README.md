# Compiling in windows:
## Tools:
Pyinstaller for creating binary
## Commands:
In windows python should be installed, verify project running:
```
python -m pip install -r req.txt
python main.py
```
## Grapheme JSON file:

```commandline
copy C:\Users\Manar\AppData\Local\Programs\Python\Python310\Lib\site-packages\grapheme\data\grapheme_break_property.json
Into ./bin file
```
Change code in grapheme to point to bin:
```python
("./bin/grapheme_break_property.json", 'r') as f:
```

## Pyinstaller
```shell
pyinstaller -c --onefile main.py
```

## Spec file:
is not used