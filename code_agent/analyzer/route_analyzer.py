"""
Route analyzer: uses Python AST parsing to inspect backend route definitions
for PayPal payment endpoints and client-token exchange routes.
"""

import ast
from pathlib import Path

from code_agent.analyzer.models import ServerEndpoint


class RouteVisitor(ast.NodeVisitor):
    """AST visitor that finds FastAPI and Flask route decorators."""

    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        self.endpoints: list[ServerEndpoint] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._check_decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._check_decorators(node)
        self.generic_visit(node)

    def _check_decorators(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            # Case: @app.get("/path"), @app.post("/path"), @router.get("/path")
            func = decorator.func
            if isinstance(func, ast.Attribute) and func.attr.lower() in ("get", "post", "put", "delete", "route"):
                method = func.attr.upper()
                if method == "ROUTE":
                    # Check methods=['POST'] argument in Flask
                    method = "GET"
                    for kw in decorator.keywords:
                        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            for elt in kw.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    method = elt.value.upper()
                                    break

                # Extract path argument (usually the first positional argument)
                path_str = None
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    if isinstance(decorator.args[0].value, str):
                        path_str = decorator.args[0].value

                if not path_str:
                    continue

                endpoint_type = "other"
                norm_path = path_str.lower().rstrip("/")
                if "client-token" in norm_path:
                    endpoint_type = "client_token"
                elif "capture" in norm_path:
                    endpoint_type = "capture_order"
                elif norm_path.endswith("/orders") or norm_path.endswith("/order"):
                    endpoint_type = "create_order"

                # Record endpoint if related to payment or api
                if endpoint_type != "other" or "/api/" in norm_path or "paypal" in norm_path:
                    self.endpoints.append(
                        ServerEndpoint(
                            file_path=self.rel_path,
                            line_number=node.lineno,
                            http_method=method,
                            path=path_str,
                            endpoint_type=endpoint_type,
                            framework="fastapi",
                        )
                    )


def analyze_python_file(file_path: Path, repo_root: Path) -> list[ServerEndpoint]:
    """Parse a single Python file and extract payment routes."""
    rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
    content = file_path.read_text(encoding="utf-8", errors="replace")

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        return []

    visitor = RouteVisitor(rel_path)
    visitor.visit(tree)
    return visitor.endpoints


def scan_routes(repo_root: Path) -> list[ServerEndpoint]:
    """Scan all Python files in the repository for payment API endpoints."""
    python_files: list[Path] = []
    candidates = list(repo_root.rglob("*.py"))
    for file_path in candidates:
        parts = file_path.relative_to(repo_root).parts  # only folders inside the repo
        if any(ignored in parts for ignored in ("venv", ".venv", "node_modules", "outputs", ".git", "tests")):
            continue
        python_files.append(file_path)

    all_endpoints: list[ServerEndpoint] = []
    for file_path in python_files:
        endpoints = analyze_python_file(file_path, repo_root)
        all_endpoints.extend(endpoints)

    return all_endpoints
