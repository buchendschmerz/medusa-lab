"""LaTeX helpers: escaping, sanitising model-written prose, templating, PDF builds.

Model-written text is *untrusted* (it may be steered by retrieved abstracts), so
it never reaches the TeX engine verbatim: only an allow-list of harmless text
and math commands survives, everything else is escaped. Builds additionally
run with shell escape disabled and ``openin_any``/``openout_any`` set to
paranoid, so a document cannot read or write files outside its directory.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2

from .utils import contains_cjk

log = logging.getLogger("medusa.latex")


class TexSafe(str):
    """A string that is already valid, sanitised LaTeX."""

    __slots__ = ()


# ----------------------------------------------------------------------------- plain escaping
_SPECIAL = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "<": r"\textless{}",
    ">": r"\textgreater{}", "|": r"\textbar{}",
}
_GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta", "η": "eta",
    "θ": "theta", "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi",
    "ρ": "rho", "σ": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega",
    "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi", "Π": "Pi", "Σ": "Sigma",
    "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
}
_MATH_SYMBOLS = {
    "≈": "approx", "≤": "leq", "≥": "geq", "≠": "neq", "±": "pm", "×": "times", "÷": "div", "→": "rightarrow",
    "←": "leftarrow", "⇒": "Rightarrow", "↔": "leftrightarrow", "∞": "infty", "∑": "sum", "∏": "prod",
    "∫": "int", "√": "surd", "∂": "partial", "∇": "nabla", "∈": "in", "∉": "notin", "⊂": "subset",
    "∪": "cup", "∩": "cap", "∀": "forall", "∃": "exists", "∝": "propto", "∼": "sim", "≡": "equiv",
    "⋅": "cdot", "·": "cdot", "⟨": "langle", "⟩": "rangle", "′": "prime", "∘": "circ", "≪": "ll", "≫": "gg",
}
_TEXT_UNICODE = {
    "\u2212": "$-$", "\u00a0": "~", "\u2009": r"\,", "\u202f": r"\,", "\u2011": "-", "\u2010": "-",
    "\u00b0": r"\textdegree{}", "\u2032": "$'$", "\u2033": "$''$", "\u2022": r"\textbullet{}",
    "\u2248": r"$\approx$", "\u2190": r"$\leftarrow$",
}
# characters pdflatex+inputenc handles natively (besides ASCII)
_PDFLATEX_OK = set("–—‘’“”…«»¡¿€£¥§¶©®™") | {chr(c) for c in range(0xA0, 0x100)}


def _unicode_to_tex(ch: str, *, unicode_ok: bool) -> str:
    if ch in _TEXT_UNICODE:
        return _TEXT_UNICODE[ch]
    if ch in _GREEK:
        return f"$\\{_GREEK[ch]}$"
    if ch in _MATH_SYMBOLS:
        return f"$\\{_MATH_SYMBOLS[ch]}$"
    if unicode_ok or ch in _PDFLATEX_OK:
        return ch
    if ch in "\u200b\u200c\u200d\ufeff":
        return ""
    return "?"  # unsupported glyph for pdflatex


def escape_text(text: Any, *, unicode_ok: bool = False) -> str:
    """Escape arbitrary text for LaTeX text mode."""
    out = []
    for ch in str(text):
        if ch in _SPECIAL:
            out.append(_SPECIAL[ch])
        elif ord(ch) < 128:
            out.append(ch if ch.isprintable() or ch in "\n\t" else " ")
        else:
            out.append(_unicode_to_tex(ch, unicode_ok=unicode_ok))
    return "".join(out)


# ----------------------------------------------------------------------------- sanitising
CITE_COMMANDS = {"cite": "citep", "citep": "citep", "citet": "citet", "citealp": "citealp",
                 "citeauthor": "citeauthor", "citeyear": "citeyear"}
REF_COMMANDS = {"ref", "eqref", "autoref"}
TEXT_ARG_COMMANDS = {"emph", "textbf", "textit", "texttt", "textsc", "underline", "subsection",
                     "subsubsection", "paragraph"}
NOARG_TEXT_COMMANDS = {"ldots", "dots", "textendash", "textemdash", "LaTeX", "TeX", "textbackslash",
                       "textasciitilde", "textasciicircum", "textbullet", "textdegree", "quad", "qquad",
                       "noindent", "newline", "par", "S"}
SYMBOL_ESCAPES = {"%", "&", "_", "#", "$", "{", "}", ",", ";", "!", " ", "/"}
MATH_COMMANDS = {
    # greek
    *{name for name in _GREEK.values()}, "varepsilon", "vartheta", "varphi", "varrho", "varsigma", "varpi",
    # operators & relations
    "frac", "dfrac", "tfrac", "sqrt", "sum", "prod", "int", "iint", "oint", "lim", "limsup", "liminf", "sup",
    "inf", "max", "min", "arg", "argmax", "argmin", "log", "ln", "exp", "sin", "cos", "tan", "tanh", "sinh",
    "cosh", "det", "Pr", "deg", "dim", "ker", "gcd", "partial", "nabla", "infty", "cdot", "cdots", "ldots",
    "dots", "vdots", "ddots", "times", "div", "pm", "mp", "leq", "le", "geq", "ge", "neq", "ne", "approx",
    "sim", "simeq", "cong", "propto", "equiv", "ll", "gg", "to", "gets", "rightarrow", "leftarrow",
    "Rightarrow", "Leftarrow", "leftrightarrow", "Leftrightarrow", "longrightarrow", "mapsto", "in", "notin",
    "ni", "subset", "subseteq", "supset", "supseteq", "cup", "cap", "setminus", "emptyset", "varnothing",
    "forall", "exists", "neg", "land", "lor", "wedge", "vee", "oplus", "otimes", "circ", "bullet", "star",
    "ast", "dagger", "top", "bot", "perp", "parallel", "mid", "nmid", "prime", "ell", "hbar", "Re", "Im",
    "aleph", "angle", "triangle", "square", "surd", "binom", "choose",
    # decorations & fonts
    "hat", "bar", "tilde", "dot", "ddot", "vec", "overline", "underline", "widehat", "widetilde",
    "overbrace", "underbrace", "mathbb", "mathbf", "mathrm", "mathcal", "mathit", "mathsf", "mathtt",
    "mathfrak", "boldsymbol", "operatorname", "text", "textrm", "textit", "textbf", "mbox",
    # delimiters & spacing
    "left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr", "langle", "rangle",
    "lfloor", "rfloor", "lceil", "rceil", "lvert", "rvert", "lVert", "rVert", "vert", "Vert", "quad",
    "qquad", "displaystyle", "textstyle", "limits", "nolimits", "begin", "end", "phantom", "underset",
    "overset", "stackrel", "not", "colon",
}
MATH_ENVS = {"cases", "aligned", "pmatrix", "bmatrix", "matrix", "vmatrix", "gathered", "split", "array"}
_CITE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:\-]{0,63}$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9:_\-.]{1,64}$")
_MATH_SPLIT = re.compile(r"(\$\$.+?\$\$|\\\[.+?\\\]|\\\(.+?\\\)|(?<!\\)\$[^$\n]+?(?<!\\)\$)", re.S)


def _read_group(s: str, i: int) -> tuple[str, int] | None:
    """If s[i] == '{', return (content, index after the matching '}')."""
    if i >= len(s) or s[i] != "{":
        return None
    depth = 0
    for j in range(i, len(s)):
        ch = s[j]
        if ch == "\\":
            continue
        if ch == "{" and (j == 0 or s[j - 1] != "\\"):
            depth += 1
        elif ch == "}" and s[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return None


@dataclass
class Sanitizer:
    """Convert model-written "LaTeX-lite / Markdown-ish" prose into safe LaTeX."""

    cite_keys: set[str] | None = None
    labels: set[str] | None = None
    unicode_ok: bool = False
    dropped: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ public
    def paragraph_text(self, text: str) -> TexSafe:
        text = (text or "").replace("\r\n", "\n").strip()
        text = re.sub(r"\\begin\{(itemize|enumerate)\}|\\end\{(itemize|enumerate)\}", "\n", text)
        text = re.sub(r"\\item\s*", "\n- ", text)
        blocks = re.split(r"\n\s*\n", text)
        return TexSafe("\n\n".join(b for b in (self._block(b) for b in blocks) if b.strip()))

    def inline(self, text: str) -> TexSafe:
        return TexSafe(self._segment(" ".join((text or "").split())))

    def math(self, expr: str) -> TexSafe | None:
        """Sanitise a bare math expression (no delimiters); None if it cannot be made safe."""
        return self._math((expr or "").strip())

    # ------------------------------------------------------------------ blocks
    def _block(self, block: str) -> str:
        lines = [ln.rstrip() for ln in block.strip().split("\n")]
        out: list[str] = []
        list_kind: str | None = None
        for line in lines:
            stripped = line.strip()
            heading = re.match(r"^#{2,6}\s+(.+)$", stripped)
            bullet = re.match(r"^(?:[-*•])\s+(.+)$", stripped)
            number = re.match(r"^\d+[.)]\s+(.+)$", stripped)
            kind = "itemize" if bullet else ("enumerate" if number else None)
            if list_kind and kind != list_kind:
                out.append(f"\\end{{{list_kind}}}")
                list_kind = None
            if heading:
                out.append(f"\\subsection*{{{self._segment(heading.group(1))}}}")
            elif kind:
                if list_kind is None:
                    out.append(f"\\begin{{{kind}}}")
                    list_kind = kind
                out.append(f"  \\item {self._segment((bullet or number).group(1))}")  # type: ignore[union-attr]
            elif stripped:
                out.append(self._segment(stripped))
        if list_kind:
            out.append(f"\\end{{{list_kind}}}")
        return "\n".join(out)

    def _segment(self, text: str) -> str:
        """Text with inline/display math."""
        parts = _MATH_SPLIT.split(text)
        out = []
        for part in parts:
            if not part:
                continue
            display = None
            if part.startswith("$$") and part.endswith("$$") and len(part) > 4 or part.startswith("\\[") and part.endswith("\\]"):
                display, body = True, part[2:-2]
            elif part.startswith("\\(") and part.endswith("\\)"):
                display, body = False, part[2:-2]
            elif part.startswith("$") and part.endswith("$") and len(part) > 2:
                display, body = False, part[1:-1]
            if display is None:
                out.append(self._text(self._markdown(part)))
                continue
            safe = self._math(body.strip())
            if safe is None:
                self.dropped.append(f"math: {body[:60]}")
                out.append(escape_text(body, unicode_ok=self.unicode_ok))
            else:
                out.append(f"\\[ {safe} \\]" if display else f"${safe}$")
        return "".join(out)

    @staticmethod
    def _markdown(text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
        text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\\emph{\1}", text)
        text = re.sub(r"(?<!`)`([^`\n]+)`(?!`)", r"\\texttt{\1}", text)
        return text

    # ------------------------------------------------------------------ text mode
    def _text(self, s: str) -> str:
        out: list[str] = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch == "\\":
                m = re.match(r"\\([A-Za-z]+)\*?|\\(.)", s[i:], re.S)
                if not m:
                    out.append(r"\textbackslash{}")
                    i += 1
                    continue
                name = m.group(1) or m.group(2)
                j = i + m.end()
                if m.group(2) is not None:  # control symbol
                    if name in SYMBOL_ESCAPES:
                        out.append("\\" + name)
                    elif name == "\\":
                        out.append("\n")
                    else:
                        out.append(escape_text("\\" + name, unicode_ok=self.unicode_ok))
                    i = j
                    continue
                if name in CITE_COMMANDS:
                    while j < n and s[j] == "[":  # optional args are dropped
                        close = s.find("]", j)
                        j = close + 1 if close != -1 else n
                    grp = _read_group(s, j)
                    if grp:
                        keys = [k.strip() for k in grp[0].split(",") if k.strip()]
                        good = [k for k in keys if _CITE_KEY_RE.match(k)
                                and (self.cite_keys is None or k in self.cite_keys)]
                        self.dropped += [f"cite:{k}" for k in keys if k not in good]
                        if good:
                            out.append(f"\\{CITE_COMMANDS[name]}{{{','.join(good)}}}")
                        i = grp[1]
                        continue
                elif name in REF_COMMANDS:
                    grp = _read_group(s, j)
                    if grp and _LABEL_RE.match(grp[0]) and (self.labels is None or grp[0] in self.labels):
                        out.append(f"\\{name}{{{grp[0]}}}")
                        i = grp[1]
                        continue
                    if grp:
                        self.dropped.append(f"ref:{grp[0]}")
                        out.append("??")
                        i = grp[1]
                        continue
                elif name in TEXT_ARG_COMMANDS:
                    grp = _read_group(s, j)
                    if grp:
                        star = "*" if name.startswith(("sub", "para")) else ""
                        out.append(f"\\{name}{star}{{{self._text(grp[0])}}}")
                        i = grp[1]
                        continue
                elif name in NOARG_TEXT_COMMANDS:
                    out.append(f"\\{name}{{}}" if name not in ("par", "newline", "noindent") else f"\\{name} ")
                    i = j
                    continue
                self.dropped.append(f"command:\\{name}")
                out.append(r"\textbackslash{}" + escape_text(name, unicode_ok=self.unicode_ok))
                i = j
                continue
            if ch == "~":  # LaTeX non-breaking space, as in "Fig.~\\ref{...}"
                out.append("~")
            elif ch in _SPECIAL:
                out.append(_SPECIAL[ch])
            elif ord(ch) < 128:
                out.append(ch if ch.isprintable() or ch == "\n" else " ")
            else:
                out.append(_unicode_to_tex(ch, unicode_ok=self.unicode_ok))
            i += 1
        return "".join(out)

    # ------------------------------------------------------------------ math mode
    def _math(self, body: str) -> TexSafe | None:
        if not body or len(body) > 3000 or "$" in body.replace("\\$", ""):
            return None
        body = "".join(f"\\{_GREEK[c]} " if c in _GREEK else (f"\\{_MATH_SYMBOLS[c]} " if c in _MATH_SYMBOLS else c)
                       for c in body)
        if any(ord(c) > 127 for c in body):
            return None
        out: list[str] = []
        i = 0
        n = len(body)
        envs: list[str] = []
        depth = 0
        while i < n:
            ch = body[i]
            if ch == "\\":
                m = re.match(r"\\([A-Za-z]+)|\\(.)", body[i:], re.S)
                if not m:
                    return None
                name = m.group(1) or m.group(2)
                j = i + m.end()
                if m.group(2) is not None:
                    if name in "{}|,;:!> \\%&#_$":
                        out.append("\\" + name)
                        i = j
                        continue
                    return None
                if name not in MATH_COMMANDS:
                    return None
                if name in ("begin", "end"):
                    grp = _read_group(body, j)
                    if not grp or grp[0] not in MATH_ENVS:
                        return None
                    if name == "begin":
                        envs.append(grp[0])
                    elif not envs or envs.pop() != grp[0]:
                        return None
                    out.append(f"\\{name}{{{grp[0]}}}")
                    i = grp[1]
                    continue
                if name in ("text", "textrm", "textit", "textbf", "mbox", "operatorname"):
                    grp = _read_group(body, j)
                    if not grp:
                        return None
                    inner = grp[0] if name != "operatorname" else re.sub(r"[^A-Za-z]", "", grp[0])
                    out.append(f"\\{name}{{{escape_text(inner)}}}")
                    i = grp[1]
                    continue
                out.append("\\" + name)
                i = j
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    return None
            elif ch == "%":
                out.append(r"\%")
                i += 1
                continue
            elif ch == "#":
                out.append(r"\#")
                i += 1
                continue
            elif ch == "&" and not envs:
                out.append(r"\&")
                i += 1
                continue
            elif ch == "~":
                out.append(" ")
                i += 1
                continue
            out.append(ch)
            i += 1
        if depth != 0 or envs:
            return None
        return TexSafe("".join(out))


_POWER = re.compile(r"(?<![\\$\w])([A-Za-z](?:_[A-Za-z]+)?|\d+(?:\.\d+)?)\^(\{[^{}$]+\}|-?[A-Za-z0-9.]*[A-Za-z0-9])")
_GREEK_WORDS = {"alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "tau", "sigma", "mu", "theta", "omega"}


def mathify(text: str) -> str:
    """Wrap plain-text powers from simulation findings (``N^1.75``, ``R^2``) in inline math."""

    def power(m: re.Match[str]) -> str:
        base, exp = m.group(1), m.group(2).strip("{}")
        if "_" in base:
            head, sub = base.split("_", 1)
            base = f"{head}_{{\\mathrm{{{sub}}}}}"
        exp = f"\\{exp}" if exp in _GREEK_WORDS else exp
        return f"${base}^{{{exp}}}$"

    text = re.sub(r"(?<=\s)~(?=\s)", r"$\\sim$", text)
    return _POWER.sub(power, text)


# ----------------------------------------------------------------------------- templating
def _finalize(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, TexSafe):
        return value
    if isinstance(value, (int, float)):
        return value
    return escape_text(value, unicode_ok=True)


def latex_env(templates_dir: Path, *, unicode_ok: bool = False) -> jinja2.Environment:
    """Jinja environment with LaTeX-friendly delimiters and escape-by-default output.

    ``\\VAR{x}`` prints (escaped unless ``x`` is :class:`TexSafe`), ``\\BLOCK{...}`` holds statements.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        block_start_string=r"\BLOCK{", block_end_string="}",
        variable_start_string=r"\VAR{", variable_end_string="}",
        comment_start_string=r"\#{", comment_end_string="}",
        line_statement_prefix="%%", line_comment_prefix="%#",
        trim_blocks=True, lstrip_blocks=True, autoescape=False, keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined, finalize=_finalize,
    )

    def tex_filter(value: Any) -> TexSafe:
        return TexSafe(escape_text(value, unicode_ok=unicode_ok))

    env.filters["tex"] = tex_filter
    env.filters["safe_tex"] = lambda v: TexSafe(v)
    return env


# ----------------------------------------------------------------------------- building
@dataclass
class BuildResult:
    ok: bool
    pdf: Path | None
    engine: str
    seconds: float
    errors: list[str] = field(default_factory=list)
    log_excerpt: str = ""


def needs_unicode_engine(text: str) -> bool:
    return contains_cjk(text)


def available_engines() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in ("latexmk", "pdflatex", "lualatex", "tectonic")}


def _plan(engine: str, unicode_doc: bool) -> list[tuple[str, list[list[str]]]]:
    """Candidate build plans (name, commands) in preference order."""
    tools = available_engines()
    flags = ["-interaction=nonstopmode", "-halt-on-error", "-file-line-error"]
    plans: list[tuple[str, list[list[str]]]] = []
    tex = "lualatex" if unicode_doc else "pdflatex"
    if engine in ("auto", "latexmk") and tools["latexmk"] and tools[tex]:
        plans.append((f"latexmk/{tex}", [["latexmk", "-lualatex" if unicode_doc else "-pdf", *flags, "paper.tex"]]))
    if engine in ("auto", tex) and tools[tex]:
        plans.append((tex, [[tex, *flags, "paper.tex"], [tex, *flags, "paper.tex"]]))
    if engine in ("auto", "tectonic") and tools["tectonic"] and not unicode_doc:
        plans.append(("tectonic", [["tectonic", "--keep-logs", "paper.tex"]]))
    return plans


_ERROR_LINE = re.compile(r"^(?:!|.*:\d+: )(.*)$")


def _extract_errors(log_text: str) -> list[str]:
    errors = []
    lines = log_text.splitlines()
    for idx, line in enumerate(lines):
        if _ERROR_LINE.match(line) and ("Error" in line or line.startswith("!") or ": " in line):
            context = " ".join(x.strip() for x in lines[idx:idx + 3])
            errors.append(context[:300])
        if len(errors) >= 6:
            break
    return errors


def build_pdf(tex_path: Path, *, engine: str = "auto", timeout: float = 300) -> BuildResult:
    """Compile ``tex_path`` (named paper.tex) inside its directory."""
    tex_path = Path(tex_path)
    workdir = tex_path.parent
    if tex_path.name != "paper.tex":
        raise ValueError("expected a file named paper.tex")
    unicode_doc = needs_unicode_engine(tex_path.read_text(encoding="utf-8"))
    plans = _plan(engine, unicode_doc)
    if not plans:
        need = "lualatex (+luatexja)" if unicode_doc else "pdflatex or tectonic"
        return BuildResult(False, None, "none", 0.0, [f"no LaTeX engine found (need {need})"])
    env = dict(os.environ)
    env.update({"shell_escape": "f", "openin_any": "p", "openout_any": "p", "max_print_line": "1000",
                "TEXMFOUTPUT": str(workdir)})
    last = BuildResult(False, None, "none", 0.0)
    for name, commands in plans:
        start = time.monotonic()
        ok = True
        output = ""
        for cmd in commands:
            try:
                proc = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True, errors="replace",
                                      timeout=timeout, stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                ok, output = False, f"{name}: timed out after {timeout}s"
                break
            output = proc.stdout + proc.stderr
            if proc.returncode != 0:
                ok = False
                break
        pdf = workdir / "paper.pdf"
        log_file = workdir / "paper.log"
        log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else output
        seconds = round(time.monotonic() - start, 2)
        if ok and pdf.exists() and pdf.stat().st_size > 0:
            _clean_aux(workdir)
            return BuildResult(True, pdf, name, seconds, [], "")
        last = BuildResult(False, None, name, seconds, _extract_errors(log_text) or [output[-500:]],
                           "\n".join(log_text.splitlines()[-40:]))
        log.warning("LaTeX build with %s failed: %s", name, last.errors[:1])
    return last


def _clean_aux(workdir: Path) -> None:
    for suffix in (".aux", ".out", ".fls", ".fdb_latexmk", ".toc", ".bbl", ".blg", ".synctex.gz", ".xdv"):
        for path in workdir.glob(f"*{suffix}"):
            path.unlink(missing_ok=True)
