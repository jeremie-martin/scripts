from typer import Typer
from rich import print

app = Typer(help="Utility scripts — run `scripts <command> --help`.")

# Light wrappers that reuse existing modules
@app.command()
def concat(patterns: list[str] = [], terminal: bool = False):
    import scripts.concat as m
    # delegate to module-level main if flags diverge; here we just call it
    m.main()

@app.command()
def transcript(urls: list[str] = []):
    import scripts.transcript as m
    m.main()

# Jama namespace
jama = Typer(help="Jama utilities")
app.add_typer(jama, name="jama")

@jama.command("clean")
def jama_clean():
    import scripts.jamaclean as m
    m.main()

@jama.command("concat")
def jama_concat():
    import scripts.jamaconcat as m
    m.main()

@jama.command("concatfull")
def jama_concatfull():
    import scripts.jamaconcatfull as m
    m.main()

@jama.command("filltests")
def jama_filltests():
    import scripts.jamafilltests as m
    m.main()

@jama.command("linking")
def jama_linking():
    import scripts.jamalinking as m
    m.main()

@jama.command("linkingfull")
def jama_linkingfull():
    import scripts.jamalinkingfull as m
    m.main()

@jama.command("notest")
def jama_notest():
    import scripts.jamanotest as m
    m.main()

@jama.command("tmp")
def jama_tmp():
    import scripts.jamatmp as m
    m.main()
