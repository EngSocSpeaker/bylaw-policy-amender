import re
from typing import cast

from PySide6.QtGui import QValidator

SECTION_RE = r'[0-9]+\.[0-9]+(?:\.[1-9][0-9]*(?:\.[a-z](?:\.([ivxlcdm]+))?)?)?'
ROMAN = [
    'i', 'ii', 'iii', 'iv', 'v',
    'vi', 'vii', 'viii', 'ix', 'x',
    'xi', 'xii', 'xiii', 'xiv', 'xv',
    'xvi', 'xvii', 'xviii', 'xix', 'xx',
]

Section = tuple[int, int, int, int, int]

def texToLines(tex: str) -> list[str]:
    lines = re.split(r'[^\S\n]*\n', tex);
    result: list[str] = []
    inList = False
    for line in lines:
        if not inList:
            result.append(line)
            if re.match(r'^\\begin\s*\{\s*easylist\s*\}', line):
                inList = True
            continue
        if re.match(r'^\s*&+', line):
            result.append(line)
            continue
        if re.match(r'^\\', line):
            result.append(line)
            if re.match(r'^\\end\s*\{\s*easylist\s*\}', line):
                inList = False
            continue
        if not line.strip():
            continue # skip completely blank lines
        result[-1] = result[-1].rstrip() + ' ' + line.strip()
    return result

def sectionsForLines(lines: list[str]) -> list[Section | None]:
    currentSection = [-1, -1, -1, -1, -1]
    result: list[Section | None] = [None] * len(lines)
    for i, line in enumerate(lines):
        if line.startswith(r'\section'):
            currentSection[0] += 1
            currentSection[1:] = [-1] * len(currentSection[1:])
            result[i] = cast(Section, tuple(currentSection))
            continue
        if line.strip().startswith('&'):
            depth = len(re.findall(r'^&+', line.strip())[0])
            currentSection[depth - 1] += 1
            currentSection[depth:] = [-1] * len(currentSection[depth:])
            result[i] = cast(Section, tuple(currentSection))
        else:
            continue # not list item
    return result

class TeXSource:

    tex: str
    lines: list[str]
    linenos: dict[Section, int]
    sections: list[Section | None]
    start2: int = 0

    def __init__(self, tex: str) -> None:
        self.tex = tex
        self.lines = texToLines(self.tex)
        self.sections = sectionsForLines(self.lines)
        self.linenos = {section: i for i, section in enumerate(self.sections)
                        if section is not None}
        self.start2 = 0 if 'Start2=0' in self.tex else 1

    def sectionToTuple(self, section: str) -> Section:
        strTuple = section.strip().strip('.').lower().split('.')
        return (
            int(strTuple[0]),
            (int(strTuple[1]) - self.start2) if len(strTuple) > 1 else -1,
            (int(strTuple[2]) - 1) if len(strTuple) > 2 else -1,
            (ord(strTuple[3]) - ord('a')) if len(strTuple) > 3 else -1,
            ROMAN.index(strTuple[4]) if len(strTuple) > 4 else -1
        )

class SectionValidator(QValidator):
    def __init__(self, tex: TeXSource) -> None:
        super().__init__()

        self.tex = tex
        print('\n'.join(map(str, sorted(self.tex.linenos.keys()))))

    def validate(self, text: str, pos: int) -> object:
        if m := re.fullmatch(SECTION_RE, text, re.I):
            if m.group(1) and m.group(1).casefold() not in ROMAN:
                # there's no way to get to a valid Roman numeral
                # by going through an invalid one
                return QValidator.State.Invalid
            section = self.tex.sectionToTuple(text)
            if section not in self.tex.linenos:
                # there's no way to get a valid section
                # by going through an invalid one
                return QValidator.State.Invalid
            return QValidator.State.Acceptable
        if re.fullmatch(SECTION_RE, text.removesuffix('.'), re.I):
            return QValidator.State.Intermediate
        if re.fullmatch(r'\d+\.?|', text):
            return QValidator.State.Intermediate
        return QValidator.State.Invalid

    def fixup(self, text: str) -> str:
        while text and self.validate(text, -1) != QValidator.State.Acceptable:
            text = text[:-1]
        return text
