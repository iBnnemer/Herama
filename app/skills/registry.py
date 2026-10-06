"""LLM-generated functions saved as standalone skills in skills/."""
import ast
import importlib.util
import json
import multiprocessing
import re
import time

from app import config

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
BANNED = {"os.system", "subprocess", "shutil.rmtree", "eval", "exec", "__import__"}

PROMPT = """Write one Python module for this task.
Rules: define `def run(**kwargs)` returning a JSON-serializable value; stdlib only; no I/O outside args; no prints.
Reply with a single ```python code block only.
Task: {task}
"""


class SkillError(ValueError):
    pass


def _index_path():
    return config.SKILLS_DIR / "index.json"


def _index() -> dict:
    p = _index_path()
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def extract(text: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def validate(code: str):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SkillError(f"syntax: {e}")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
        raise SkillError("missing run()")
    src = ast.unparse(tree)
    hit = [b for b in BANNED if re.search(rf"\b{re.escape(b)}\b", src)]
    if hit:
        raise SkillError(f"banned: {hit}")


def save(name: str, code: str, desc: str = "") -> dict:
    if not NAME_RE.match(name):
        raise SkillError("bad name")
    validate(code)
    config.SKILLS_DIR.mkdir(exist_ok=True)
    (config.SKILLS_DIR / f"{name}.py").write_text(f'"""{desc}"""\n{code}', "utf-8")
    idx = _index()
    idx[name] = {"desc": desc, "ts": time.time()}
    _index_path().write_text(json.dumps(idx, ensure_ascii=False, indent=1), "utf-8")
    return {"name": name, **idx[name]}


def generate(engine, model: str, name: str, task: str) -> dict:
    out = "".join(c for c in engine.generate(model, PROMPT.format(task=task),
                                             {"temperature": 0.2, "num_predict": 1024}, False)
                  if isinstance(c, str))
    return save(name, extract(out), task)


def list_skills() -> dict:
    return _index()


def _sandbox_worker(path: str, args: dict, q: multiprocessing.Queue):
    try:
        spec = importlib.util.spec_from_file_location("_skill", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        q.put(("ok", mod.run(**args)))
    except Exception as e:
        q.put(("err", str(e)))


def run(name: str, args: dict):
    if not config.SKILL_EXEC:
        raise SkillError("exec disabled (set HERAMA_SKILL_EXEC=1)")
    if name not in _index():
        raise SkillError("unknown skill")
    path = str(config.SKILLS_DIR / f"{name}.py")
    q: multiprocessing.Queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=_sandbox_worker, args=(path, args, q), daemon=True)
    p.start()
    p.join(config.SKILL_TIMEOUT)
    if p.is_alive():
        p.kill()
        raise SkillError(f"timeout ({config.SKILL_TIMEOUT}s)")
    if q.empty():
        raise SkillError("worker exited without result")
    status, val = q.get()
    if status == "err":
        raise SkillError(val)
    return val
