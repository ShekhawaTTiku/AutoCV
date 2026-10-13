"""Global constants, file limits, and LaTeX command definitions."""

MAX_UPLOAD = 20 * 1024 * 1024
MAX_EXTRACTED = 50 * 1024 * 1024
MAX_FILES = 500
MAX_LOG = 100_000

SECTION_COMMANDS = {"section", "subsection", "subsubsection", "cvsection", "resumeSection"}

PROTECTED = {
    "documentclass", "usepackage", "RequirePackage", "geometry", "newgeometry",
    "newcommand", "renewcommand", "providecommand", "def", "gdef", "edef", "xdef",
    "let", "catcode", "input", "include", "includeonly", "endinput", "write",
    "openout", "openin", "read", "special", "directlua", "latelua", "luaexec",
    "immediate", "csname", "loop", "repeat", "font", "setlength", "addtolength",
    "vspace", "hspace", "fontsize", "linespread", "pagestyle", "pagecolor",
}

TEXT_EXTENSIONS = {
    ".tex", ".sty", ".cls", ".bib", ".cfg", ".def", ".clo", ".fd", ".bst",
    ".bbx", ".cbx", ".ltx", ".tikz", ".txt",
}
