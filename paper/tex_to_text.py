"""Render main.tex as plain text in reading order.

The two-column PDF does not copy-paste cleanly, so the text version is built from
the LaTeX source instead: sections and subsections are numbered as they appear in
the paper, citation keys are resolved to their bracket numbers, tables are laid
out as fixed-width columns, and figure captions are kept in place.

    python3 tex_to_text.py > main.txt
"""

import re
import sys
import textwrap

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]
WRAP = 88


def render_tabular(block):
    """Turn the tabular body of a table float into aligned fixed-width columns."""
    m = re.search(r"\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}", block, re.S)
    if not m:
        return ""
    rows = []
    for raw in m.group(1).split(r"\\"):
        line = re.sub(r"\\(toprule|midrule|bottomrule|cmidrule\(lr\)\{[^}]*\})", "", raw)
        line = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}\{([^}]*)\}", r"\1", line)
        line = clean_inline(line).strip()
        if not line:
            continue
        rows.append([c.strip() for c in line.split("&")])
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    colw = [max(len(r[i]) for r in rows) for i in range(width)]
    return "\n".join("  ".join(c.ljust(colw[i]) for i, c in enumerate(r)).rstrip()
                     for r in rows)


def clean_inline(s):
    """Strip the inline markup that survives into running text."""
    s = s.replace(r"\&", "&").replace(r"\%", "%").replace(r"\_", "_")
    for a, b in ((r"v_{\min}", "v_min"), (r"v_{\max}", "v_max"),
                 (r"\lambda_{\max}", "lambda_max"), (r"\Delta t", "dt"),
                 (r"S_i^{\mathrm{rated}}", "S_rated"), (r"\times", "x"),
                 (r"\le", "<="), (r"\pm", "+/-")):
        s = s.replace(a, b)
    s = re.sub(r'\\"\{?([a-zA-Z])\}?', r"\1", s)      # \"u  -> u
    s = re.sub(r"\\~\{?([a-zA-Z])\}?", r"\1", s)      # \~n  -> n
    s = s.replace(r"\,", "")
    s = s.replace("~", " ").replace("---", "-").replace("--", "-")
    s = s.replace("``", '"').replace("''", '"')
    s = re.sub(r"\\(emph|textit|textbf|text)\{([^{}]*)\}", r"\2", s)
    s = re.sub(r"\\(times|le|ge|pm|max|min|sum|sqrt|Delta|lambda|mathrm|cdot)\b", "", s)
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "").replace("$", "")
    return re.sub(r"[ \t]+", " ", s)


def main():
    src = open("main.tex").read()
    keys = re.findall(r"\\bibitem\{(\w+)\}", src)
    num = {k: str(i + 1) for i, k in enumerate(keys)}

    title = " ".join(re.search(r"\\title\{(.*?)\}", src, re.S).group(1).split())
    # the template gives every author their own name+affiliation pair
    blocks = re.findall(r"\\IEEEauthorblockN\{(.*?)\}\s*\n\s*"
                        r"\\IEEEauthorblockA\{(.*?)\}\s*\n", src, re.S)

    body = src[src.index(r"\begin{abstract}"):src.index(r"\begin{thebibliography}")]

    # Pre-pass: resolve \label targets to the numbers a reader sees, walking the
    # source in order so section, figure and table counters stay in step.
    labels, here = {}, ""
    s_i, b_i, fig_i, tab_i = 0, 0, 0, 0
    token = re.compile(r"\\section\{|\\subsection\{|\\begin\{(figure|table)\*?\}"
                       r"|\\label\{([^}]*)\}")
    depth_float = None
    for m in token.finditer(body):
        t = m.group(0)
        if t.startswith(r"\section"):
            s_i += 1
            b_i = 0
            here, depth_float = ROMAN[s_i - 1], None
        elif t.startswith(r"\subsection"):
            b_i += 1
            here, depth_float = f"{ROMAN[s_i-1]}-{chr(64+b_i)}", None
        elif t.startswith(r"\begin{figure"):
            fig_i += 1
            depth_float = str(fig_i)
        elif t.startswith(r"\begin{table"):
            tab_i += 1
            depth_float = ROMAN[tab_i - 1]
        else:
            labels[m.group(2)] = depth_float if depth_float else here
            depth_float = None

    body = re.sub(r"\\cite\{([^}]*)\}",
                  lambda m: "[" + ", ".join(num.get(k.strip(), "?")
                                            for k in m.group(1).split(",")) + "]", body)
    body = re.sub(r"\\ref\{([^}]*)\}", lambda m: labels.get(m.group(1), "?"), body)

    # floats -> markers, before any other stripping
    fig_n, tab_n = [0], [0]

    def fig_repl(m):
        fig_n[0] += 1
        return f"\n@@FIG@@{fig_n[0]}. " + " ".join(m.group(1).split()) + "\n"

    body = re.sub(r"\\begin\{figure\*?\}.*?\\caption\{(.*?)\}.*?\\end\{figure\*?\}",
                  fig_repl, body, flags=re.S)

    def table_repl(m):
        tab_n[0] += 1
        cap = f"{ROMAN[tab_n[0]-1]}. " + " ".join(m.group(1).split())
        return "\n@@TAB@@" + cap + "\n@@GRID@@" + render_tabular(m.group(2)) + "@@END@@\n"

    body = re.sub(r"\\begin\{table\*?\}.*?\\caption\{(.*?)\}(.*?)\\end\{table\*?\}",
                  table_repl, body, flags=re.S)

    sec, sub = [0], [0]

    def heading(m):
        # one pass over both levels, so the subsection letter resets per section
        if m.group(1) == "section":
            sec[0] += 1
            sub[0] = 0
            return f"\n@@H1@@{ROMAN[sec[0]-1]}. {m.group(2).upper()}\n"
        sub[0] += 1
        return f"\n@@H2@@{chr(64+sub[0])}. {m.group(2)}\n"

    body = re.sub(r"\\(section|subsection)\{(.*?)\}", heading, body)
    body = body.replace(r"\begin{abstract}", "\n@@H1@@ABSTRACT\n")
    body = body.replace(r"\end{abstract}", "")
    body = re.sub(r"\\begin\{IEEEkeywords\}", "\n@@H1@@INDEX TERMS\n", body)
    body = body.replace(r"\end{IEEEkeywords}", "")
    body = re.sub(r"\\begin\{itemize\}|\\end\{itemize\}", "", body)
    body = body.replace(r"\item", "@@LI@@")
    def equation(m):
        """LaTeX math does not survive a generic strip, so map the macros first."""
        e = re.sub(r"\\label\{[^}]*\}", "", m.group(1))
        for a, b in ((r"\mathrm{IV}", "IV"), (r"\sum_{h}", "sum_h "),
                     (r"\sum_{p}", "sum_p"), (r"\max", "max"), (r"\Delta t", "dt"),
                     (r"\Big[", "["), (r"\Big]", "]"),
                     (r"v_{\min}", "v_min"), (r"v_{\max}", "v_max"),
                     (r"v_{p,h}", "v_ph")):
            e = e.replace(a, b)
        e = re.sub(r"\\[a-zA-Z]+", "", e).replace("{", "").replace("}", "")
        return "\n@@EQ@@" + " ".join(e.split()) + "\n"

    body = re.sub(r"\\begin\{equation\}(.*?)\\end\{equation\}", equation,
                  body, flags=re.S)
    body = re.sub(r"\\eqref\{[^}]*\}", "(1)", body)   # the paper has one numbered equation
    body = re.sub(r"\\label\{[^}]*\}", "", body)

    byline = []
    for name, aff in blocks:
        byline.append(clean_inline(" ".join(name.split())).strip())
        byline += [clean_inline(ln).strip()
                   for ln in aff.replace(r"\\", "\n").splitlines() if ln.strip()]
        byline.append("")
    out = [clean_inline(title), ""] + byline
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if para.startswith("@@GRID@@"):
            continue
        for chunk in re.split(r"(@@H1@@[^\n]*|@@H2@@[^\n]*|@@FIG@@[^\n]*|"
                              r"@@TAB@@[^\n]*|@@EQ@@[^\n]*|@@GRID@@.*?@@END@@)",
                              para, flags=re.S):
            chunk = chunk.strip()
            if not chunk:
                continue
            if chunk.startswith("@@H1@@"):
                out += ["", chunk[6:], "-" * len(chunk[6:])]
            elif chunk.startswith("@@H2@@"):
                out += ["", chunk[6:]]
            elif chunk.startswith("@@FIG@@"):
                out += ["", textwrap.fill("Fig. " + chunk[7:], WRAP)]
            elif chunk.startswith("@@TAB@@"):
                out += ["", textwrap.fill("TABLE " + chunk[7:], WRAP)]
            elif chunk.startswith("@@GRID@@"):
                out += ["", chunk[8:-7].strip("\n")]
            elif chunk.startswith("@@EQ@@"):
                out += ["", "    " + chunk[6:]]
            else:
                for li in chunk.split("@@LI@@"):
                    li = clean_inline(" ".join(li.split())).strip()
                    if li:
                        pre = "  - " if "@@LI@@" in chunk else ""
                        out += ["", textwrap.fill(li, WRAP,
                                                  initial_indent=pre,
                                                  subsequent_indent="    " if pre else "")]

    out += ["", "", "REFERENCES", "----------"]
    for i, k in enumerate(keys):
        m = re.search(r"\\bibitem\{" + k + r"\}(.*?)(?=\\bibitem|\\end\{thebibliography\})",
                      src, re.S)
        entry = clean_inline(" ".join(m.group(1).split())).strip()
        out += ["", textwrap.fill(f"[{i+1}] {entry}", WRAP, subsequent_indent="    ")]

    text = "\n".join(out)
    sys.stdout.write(re.sub(r"\n{3,}", "\n\n", text) + "\n")


if __name__ == "__main__":
    main()
