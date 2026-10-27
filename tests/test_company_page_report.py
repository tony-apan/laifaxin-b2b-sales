"""一页公司全明细只读链回归：真实 CLI collect→AI 判断→render + 本地 HTTP 替身。

覆盖（任务书 AC5）：列表 10+详情 10、页面 7 条照实、详情部分失败不弃整页、缺 id/中文/域名、
注入 URL、重复 id、错 source、漏判、外来 id、评分字段；断言 fake token 不进输出/文件/argv，
只有允许的两个只读 API 路径被调用，无平台写 API。
"""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "company_page_report.py"
TOKEN = "FAKETOKEN-DO-NOT-LEAK-0000&SEG2&SEG3"
ORG = "FAKEORG-0001"
KEYWORD = "pet food wholesale distributor query"
IDS = ["%032x" % i for i in range(1, 11)]
ALLOWED = {"/api/refine/company-list", "/api/domain/base-info"}


class _Handler(BaseHTTPRequestHandler):
    state = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        st = _Handler.state
        st["paths"].append(self.path)
        if self.path not in ALLOWED:
            st["violations"].append(self.path)
            self._reply(404, {"success": False})
            return
        if self.path == "/api/refine/company-list":
            st["list_bodies"].append(body)
            self._reply(200, st["list_resp"](body))
            return
        resp = st["details"].get(body.get("domain"))
        if resp is None:
            self._reply(404, {"success": False, "message": "unknown id"})
            return
        self._reply(200, resp)

    def _reply(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def _run(args, stdin=None):
    from tests.gate_env import gate_test_env
    import os
    env = dict(os.environ, **gate_test_env(), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(TOOL)] + args, input=stdin,
                          capture_output=True, text=True, timeout=180, cwd=str(ROOT), env=env)


def _lrow(i, name=None, zh=None, with_id=True):
    d = {}
    if with_id:
        d["id"] = IDS[i - 1]
    d["company_name"] = name if name is not None else "Pet Wholesale %d Co" % i
    d["country_code"] = "US"
    d["summary_zh"] = zh if zh is not None else "第%d家：专注宠物食品与用品批发分销，覆盖连锁零售渠道。" % i
    return d


def _dok(i, domain=None, zh=None):
    return {"success": True, "data": {
        "domain": domain if domain is not None else "shop%d.example.com" % i,
        "company_name": "Pet Wholesale %d Co" % i,
        "summary_zh": zh if zh is not None else "第%d家详情：宠物食品分销商，经营十年以上。" % i,
        "country_code": "US", "employee_count": str(5 * i)}}


def _base_judgments(doc):
    out = []
    for r in doc["rows"]:
        if (r.get("summary_zh") or "").strip():
            out.append({"company_id": r["company_id"], "matched": True,
                        "reason": "中文理由：描述与目标买家画像相符。",
                        "suggestion": "中文建议：列入本页候选，先发首封邮件。", "recommended": False})
        else:
            out.append({"company_id": r["company_id"], "matched": None, "reason": "", "suggestion": ""})
    return {"source_sha256": doc["source_sha256"], "judgments": out}


def _write_judgments(tmp, jud):
    jf = Path(tmp) / "judge.json"
    jf.write_text(json.dumps(jud, ensure_ascii=False), encoding="utf-8")
    return jf


class CompanyPageReportTest(unittest.TestCase):
    def _setup(self, tmp):
        _Handler.state = {"paths": [], "violations": [], "list_bodies": [], "details": {},
                          "list_resp": lambda b: {"success": True, "data": {"list": [], "total": 0}}}
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        ctx = Path(tmp) / "ctx.json"
        ctx.write_text(json.dumps({"base_url": "http://127.0.0.1:%d" % srv.server_address[1]}),
                       encoding="utf-8")
        return ctx

    def _collect(self, ctx, out, page=3):
        return _run(["collect", "--keyword", KEYWORD, "--page", str(page),
                     "--credentials-stdin", "--api-context", str(ctx), "--out", str(out)],
                    stdin="token=%s\norg=%s\n" % (TOKEN, ORG))

    def _render(self, tmp, src, jud, kind="临界页"):
        jf = _write_judgments(tmp, jud)
        out = Path(tmp) / "tmp-report.md"
        proc = _run(["render", "--source", str(src), "--judgments", str(jf),
                     "--page-kind", kind, "--out", str(out)])
        return proc, (out.read_text(encoding="utf-8") if out.exists() else "")

    def _assert_no_leak(self, *texts):
        for t in texts:
            self.assertNotIn(TOKEN, t)
            self.assertNotIn(ORG, t)

    def test_full_chain_collect_then_ai_judge_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._setup(tmp)
            names = {10: "Alpha|Beta\nGamma Co"}
            zhs = {9: ""}
            _Handler.state["list_resp"] = lambda b: {"success": True, "data": {
                "list": [_lrow(i, name=names.get(i), zh=zhs.get(i)) for i in range(1, 11)], "total": 25}}
            _Handler.state["details"] = {IDS[i - 1]: _dok(i, zh=zhs.get(i)) for i in range(1, 11)}
            out = Path(tmp) / "src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 0, p.stderr)
            self._assert_no_leak(p.stdout, p.stderr, out.read_text(encoding="utf-8"))
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(doc["row_count"], 10)
            self.assertEqual(doc["provenance"]["detail_ok"], 10)
            self.assertEqual(doc["provenance"]["detail_failed"], 0)
            self.assertEqual([r["url"] for r in doc["rows"]],
                             ["https://shop%d.example.com" % i for i in range(1, 11)])
            self.assertEqual(set(r["company_id"] for r in doc["rows"]), set(IDS))
            self.assertEqual(doc["rows"][8]["summary_zh"], "")
            self.assertEqual(doc["rows"][0]["size"], "5")
            self.assertEqual(set(_Handler.state["paths"]), ALLOWED)
            self.assertEqual(_Handler.state["violations"], [])
            self.assertEqual(_Handler.state["paths"].count("/api/refine/company-list"), 1)
            self.assertEqual(_Handler.state["paths"].count("/api/domain/base-info"), 10)
            lb = _Handler.state["list_bodies"][0]
            self.assertEqual(lb["keyword"], KEYWORD)
            self.assertEqual(lb["current"], 3)
            self.assertEqual(lb["pageSize"], 10)
            self.assertEqual(lb["logic"], "and")
            self.assertEqual(set(lb["filters"][0]["values"]), {"CN", "TW", "HK", "MO"})
            jud = _base_judgments(doc)
            jud["judgments"][0]["recommended"] = True
            rp, md = self._render(tmp, out, jud)
            self.assertEqual(rp.returncode, 0, rp.stderr)
            self.assertIn("第 3 页", md)
            self.assertIn("临界页", md)
            self.assertIn("10 家", md)
            self.assertIn("[shop1.example.com](https://shop1.example.com)", md)
            self.assertIn("最推荐", md)
            self.assertIn("待 AI 判断", md)
            self.assertIn("Alpha\\|Beta", md)
            table = [l for l in md.splitlines() if l.startswith("|")]
            self.assertEqual(len(table), 12)
            for rid in IDS:
                self.assertNotIn(rid, md)
            self.assertNotIn(doc["source_sha256"], md)
            self.assertNotIn(KEYWORD, md)
            self.assertNotIn("query_en", md)
            self._assert_no_leak(md, rp.stdout, rp.stderr)
            # 安全反例系列：render 必须逐一拒绝
            def reject(mutate, needle):
                j = _base_judgments(doc)
                mutate(j)
                proc, _ = self._render(tmp, out, j)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn(needle, proc.stderr)
            reject(lambda j: j.__setitem__("source_sha256", "0" * 64), "source_sha256")
            reject(lambda j: j["judgments"].append({"company_id": "f" * 32, "matched": None,
                                                    "reason": "", "suggestion": ""}), "外来")
            reject(lambda j: j["judgments"].append(dict(j["judgments"][0])), "重复")
            reject(lambda j: j["judgments"].pop(), "漏判")
            reject(lambda j: j["judgments"][1].__setitem__("score", 9), "score")
            reject(lambda j: j["judgments"][0].__setitem__("reason", "   "), "reason")
            reject(lambda j: j["judgments"][0].__setitem__("reason", "all english words"), "中文")
            reject(lambda j: j["judgments"][8].__setitem__("matched", True), "中文描述")
            reject(lambda j: [x.__setitem__("matched", False) for x in j["judgments"]],
                   "recommended" if False else "matched")
            two = lambda j: (j["judgments"][1].__setitem__("recommended", True),
                             j["judgments"][2].__setitem__("recommended", True))
            reject(two, "recommend")
            # 源被改动 → 哈希不符拒绝
            bad = json.loads(out.read_text(encoding="utf-8"))
            bad["rows"][0]["company_name"] += "X"
            badf = Path(tmp) / "bad.json"
            badf.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            proc, _ = self._render(tmp, badf, _base_judgments(bad))
            self.assertEqual(proc.returncode, 2)
            self.assertIn("source_sha256", proc.stderr)

    def test_page_returns_seven(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._setup(tmp)
            _Handler.state["list_resp"] = lambda b: {"success": True, "data": {
                "list": [_lrow(i) for i in range(1, 8)], "total": 7}}
            _Handler.state["details"] = {IDS[i - 1]: _dok(i) for i in range(1, 8)}
            out = Path(tmp) / "src.json"
            p = self._collect(ctx, out, page=5)
            self.assertEqual(p.returncode, 0, p.stderr)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(doc["row_count"], 7)
            self.assertEqual(_Handler.state["paths"].count("/api/domain/base-info"), 7)
            rp, md = self._render(tmp, out, _base_judgments(doc), kind="候选页")
            self.assertEqual(rp.returncode, 0, rp.stderr)
            self.assertIn("第 5 页", md)
            self.assertIn("7 家", md)
            self.assertEqual(len([l for l in md.splitlines() if l.startswith("|")]), 9)
            self.assertIn("没有可靠推荐", md)

    def test_detail_partial_failure_keeps_other_companies(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._setup(tmp)
            _Handler.state["list_resp"] = lambda b: {"success": True, "data": {
                "list": [_lrow(i) for i in range(1, 11)], "total": 25}}
            details = {IDS[i - 1]: _dok(i) for i in range(1, 11)}
            details[IDS[2]] = {"success": False, "message": "接口间歇空"}
            details[IDS[6]] = {"success": False, "message": "接口间歇空"}
            _Handler.state["details"] = details
            out = Path(tmp) / "src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 0, p.stderr)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(doc["row_count"], 10)
            self.assertEqual(doc["provenance"]["detail_failed"], 2)
            for idx in (2, 6):
                self.assertEqual(doc["rows"][idx]["detail_status"], "failed")
                self.assertEqual(doc["rows"][idx]["url"], "")
            self.assertEqual(doc["rows"][0]["url"], "https://shop1.example.com")
            rp, md = self._render(tmp, out, _base_judgments(doc))
            self.assertEqual(rp.returncode, 0, rp.stderr)
            self.assertEqual(len([l for l in md.splitlines() if l.startswith("|")]), 12)

    def test_collect_missing_or_duplicate_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._setup(tmp)
            _Handler.state["list_resp"] = lambda b: {"success": True, "data": {
                "list": [_lrow(i, with_id=(i != 4)) for i in range(1, 6)], "total": 5}}
            _Handler.state["details"] = {IDS[i - 1]: _dok(i) for i in range(1, 6)}
            out = Path(tmp) / "src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 2)
            self.assertIn("缺 id", p.stderr)
            self.assertFalse(out.exists())
            rows = [_lrow(i) for i in range(1, 6)]
            rows[4]["id"] = IDS[0]
            _Handler.state["list_resp"] = lambda b: {"success": True, "data": {"list": rows, "total": 5}}
            p2 = self._collect(ctx, out)
            self.assertEqual(p2.returncode, 2)
            self.assertIn("重复", p2.stderr)
            self.assertFalse(out.exists())

    def test_unsafe_domain_injection_marks_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._setup(tmp)
            _Handler.state["list_resp"] = lambda b: {"success": True, "data": {
                "list": [_lrow(i) for i in range(1, 8)], "total": 7}}
            details = {IDS[i - 1]: _dok(i) for i in range(1, 8)}
            details[IDS[4]] = _dok(5, domain="javascript:alert(1)")
            details[IDS[5]] = _dok(6, domain="data:text/html,<b>x</b>")
            details[IDS[6]] = _dok(7, domain="evil\n.com")
            _Handler.state["details"] = details
            out = Path(tmp) / "src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 0, p.stderr)
            doc = json.loads(out.read_text(encoding="utf-8"))
            for idx in (4, 5, 6):
                self.assertEqual(doc["rows"][idx]["detail_status"], "no_domain")
                self.assertEqual(doc["rows"][idx]["url"], "")
            rp, md = self._render(tmp, out, _base_judgments(doc))
            self.assertEqual(rp.returncode, 0, rp.stderr)
            self.assertNotIn("javascript:", md)
            self.assertNotIn("data:", md)

    def test_remote_api_context_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._setup(tmp)
            bad = Path(tmp) / "bad-ctx.json"
            bad.write_text(json.dumps({"base_url": "https://web.laifaxin.com"}), encoding="utf-8")
            p = _run(["collect", "--keyword", KEYWORD, "--page", "1", "--credentials-stdin",
                      "--api-context", str(bad), "--out", str(Path(tmp) / "x.json")],
                     stdin="token=%s\norg=%s\n" % (TOKEN, ORG))
            self.assertEqual(p.returncode, 2)
            self.assertIn("loopback", p.stderr)
            self.assertEqual(_Handler.state["paths"], [])

    def test_source_hygiene_static(self):
        src = TOOL.read_text(encoding="utf-8")
        self.assertNotIn('"--token"', src)
        self.assertNotIn("web.laifaxin.com", src)
        self.assertNotIn("subprocess", src)
        self.assertNotIn("getenv", src)
        self.assertIn("api_base_url", src)
        self.assertIn("credential_input", src)
        self.assertIn("session_store", src)


class _R2Handler(BaseHTTPRequestHandler):
    state = {}

    def do_POST(self):
        st = _R2Handler.state
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        st["paths"].append(self.path)
        if st.get("redirect_list") and self.path == "/api/refine/company-list":
            self._redirect(st["redirect_list"])
            return
        if self.path == "/api/refine/company-list":
            st["list_bodies"].append(body)
            self._reply(200, st["list_resp"](body))
            return
        dr = st.get("redirect_detail")
        if dr and body.get("domain") in dr:
            self._redirect(st["redirect_to"])
            return
        resp = st["details"].get(body.get("domain"))
        if resp is None:
            self._reply(404, {"success": False})
            return
        self._reply(200, resp)

    def _redirect(self, to):
        self.send_response(302)
        self.send_header("Location", to + "/api/x")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _reply(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class _CountHandler(BaseHTTPRequestHandler):
    hits = 0

    def _bump(self):
        _CountHandler.hits += 1
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self):
        self._bump()

    def do_GET(self):
        self._bump()

    def log_message(self, *a):
        pass


class R2CompanyPageReportTest(unittest.TestCase):
    """R2 反例：3xx 禁跟、四区必排除、scope 绑定、>10 异常、id 矛盾、坏类型、坏 page、空页照实。"""

    def _setup(self, tmp):
        _R2Handler.state = {"paths": [], "list_bodies": [], "details": {},
                            "list_resp": lambda b: {"success": True, "data": {"list": [], "total": 0}}}
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _R2Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        bsrv = ThreadingHTTPServer(("127.0.0.1", 0), _CountHandler)
        _CountHandler.hits = 0
        threading.Thread(target=bsrv.serve_forever, daemon=True).start()
        self.addCleanup(bsrv.server_close)
        self.addCleanup(bsrv.shutdown)
        b = "http://127.0.0.1:%d" % bsrv.server_address[1]
        ctx = Path(tmp) / "r2ctx.json"
        ctx.write_text(json.dumps({"base_url": "http://127.0.0.1:%d" % srv.server_address[1]}),
                       encoding="utf-8")
        return ctx, b

    def _collect(self, ctx, out, page="1", exclude=None, keyword=KEYWORD):
        args = ["collect", "--keyword", keyword, "--page", page,
                "--credentials-stdin", "--api-context", str(ctx), "--out", str(out)]
        if exclude is not None:
            args += ["--exclude", exclude]
        return _run(args, stdin="token=%s\norg=%s\n" % (TOKEN, ORG))

    def _render(self, tmp, src, jud, kind="候选页"):
        jf = Path(tmp) / "tmp-r2-judge.json"
        jf.write_text(json.dumps(jud, ensure_ascii=False), encoding="utf-8")
        out = Path(tmp) / "tmp-r2-out.md"
        proc = _run(["render", "--source", str(src), "--judgments", str(jf),
                     "--page-kind", kind, "--out", str(out)])
        return proc, (out.read_text(encoding="utf-8") if out.exists() else "")

    def _rows(self, n, start=1):
        rows = []
        for i in range(start, start + n):
            r = _lrow(i if i <= len(IDS) else len(IDS))
            r["id"] = "%032x" % i
            rows.append(r)
        return rows

    def _doks(self, n, start=1):
        return {IDS[i - 1]: _dok(i) for i in range(start, start + n)}

    def test_list_302_no_follow_no_file_no_external_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, b = self._setup(tmp)
            _R2Handler.state["redirect_list"] = b
            out = Path(tmp) / "tmp-r2-src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertFalse(out.exists())
            self.assertIn("302", p.stderr)
            self.assertNotIn(TOKEN, p.stderr)
            self.assertEqual(_CountHandler.hits, 0, "3xx 必须就地拒绝，绝不带凭据跟随")

    def test_detail_302_only_that_row_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, b = self._setup(tmp)
            _R2Handler.state["list_resp"] = lambda x: {"success": True, "data": {"list": self._rows(3), "total": 3}}
            _R2Handler.state["details"] = self._doks(3)
            _R2Handler.state["redirect_detail"] = {IDS[1]}
            _R2Handler.state["redirect_to"] = b
            out = Path(tmp) / "tmp-r2-src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(_CountHandler.hits, 0)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(doc["rows"][1]["detail_status"], "failed")
            self.assertEqual(doc["rows"][1]["url"], "")
            self.assertEqual(doc["rows"][0]["detail_status"], "ok")
            self.assertEqual(doc["rows"][2]["detail_status"], "ok")

    def test_exclude_empty_or_missing_mandatory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _b = self._setup(tmp)
            out = Path(tmp) / "tmp-r2-src.json"
            for bad in ("", "  ", "US", "us,de"):
                p = self._collect(ctx, out, exclude=bad)
                self.assertEqual(p.returncode, 2, bad)
                self.assertIn("四区", p.stderr)
                self.assertFalse(out.exists())
            self.assertEqual(_R2Handler.state["paths"], [], "参数拒绝必须发生在任何请求之前")
            _R2Handler.state["list_resp"] = lambda x: {"success": True, "data": {"list": self._rows(2), "total": 2}}
            _R2Handler.state["details"] = self._doks(2)
            p = self._collect(ctx, out, exclude="cn, tw, HK,mo,US")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(set(_R2Handler.state["list_bodies"][-1]["filters"][0]["values"]),
                             {"CN", "TW", "HK", "MO", "US"})

    def test_source_scope_and_filters_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _b = self._setup(tmp)
            _R2Handler.state["list_resp"] = lambda x: {"success": True, "data": {"list": self._rows(3), "total": 9}}
            _R2Handler.state["details"] = self._doks(3)
            out = Path(tmp) / "tmp-r2-src.json"
            self.assertEqual(self._collect(ctx, out).returncode, 0)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("request", doc)
            self.assertEqual(doc["request"]["current"], 1)
            self.assertEqual(doc["request"]["pageSize"], 10)
            self.assertEqual(doc["request"]["logic"], "and")
            self.assertEqual(set(doc["request"]["filters"][0]["values"]), {"CN", "TW", "HK", "MO"})
            t1 = json.loads(json.dumps(doc))
            t1["request"]["filters"][0]["values"] = ["US"]
            f1 = Path(tmp) / "tmp-r2-t1.json"
            f1.write_text(json.dumps(t1, ensure_ascii=False), encoding="utf-8")
            p, _ = self._render(tmp, f1, _base_judgments(t1))
            self.assertEqual(p.returncode, 2)
            self.assertIn("source_sha256", p.stderr)
            import importlib.util
            spec = importlib.util.spec_from_file_location("cpr_mod", TOOL)
            cpr = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cpr)
            t2 = json.loads(json.dumps(doc))
            t2["request"]["filters"][0]["values"] = ["US"]
            core = {k: t2.get(k) for k in ("schema", "source_kind", "page", "keyword", "row_count",
                                           "requested_page_size", "request", "scope_sha256",
                                           "platform_total", "provenance", "rows")}
            t2["source_sha256"] = cpr._sha256_text(cpr._canonical(core))
            f2 = Path(tmp) / "tmp-r2-t2.json"
            f2.write_text(json.dumps(t2, ensure_ascii=False), encoding="utf-8")
            p2, _ = self._render(tmp, f2, _base_judgments(t2))
            self.assertEqual(p2.returncode, 2)
            self.assertIn("scope_sha256", p2.stderr)

    def test_list_over_ten_rows_is_anomaly_exit2(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _b = self._setup(tmp)
            out = Path(tmp) / "tmp-r2-src.json"
            for n in (12, 25):
                _R2Handler.state["list_resp"] = lambda x, n=n: {"success": True, "data": {"list": self._rows(n), "total": 99}}
                p = self._collect(ctx, out)
                self.assertEqual(p.returncode, 2, n)
                self.assertIn("异常", p.stderr)
                self.assertFalse(out.exists(), n)

    def test_detail_id_mismatch_marks_row_and_keeps_list_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _b = self._setup(tmp)
            rows = self._rows(2)
            rows[0]["summary_zh"] = ""
            _R2Handler.state["list_resp"] = lambda x: {"success": True, "data": {"list": rows, "total": 2}}
            details = self._doks(2)
            details[IDS[0]] = {"success": True, "data": {
                "id": "f" * 32, "domain": "evil.example.com", "summary_zh": "别人的中文描述",
                "company_name": "Other Co", "employee_count": 999}}
            _R2Handler.state["details"] = details
            out = Path(tmp) / "tmp-r2-src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 0, p.stderr)
            doc = json.loads(out.read_text(encoding="utf-8"))
            r0 = doc["rows"][0]
            self.assertEqual(r0["detail_status"], "id_mismatch")
            self.assertEqual(r0["url"], "")
            self.assertEqual(r0["domain"], "")
            self.assertEqual(r0["summary_zh"], "", "不得嫁接别人的中文描述")
            self.assertEqual(r0["size"], "未知")

    def test_wrong_field_types_map_to_unknown_not_repr(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _b = self._setup(tmp)
            row = _lrow(1)
            row["company_name"] = {"x": 1}
            row["country_code"] = True
            row["employee_count"] = -5
            row["summary_zh"] = 123
            _R2Handler.state["list_resp"] = lambda x: {"success": True, "data": {"list": [row], "total": 1}}
            _R2Handler.state["details"] = {IDS[0]: {"success": True, "data": {
                "domain": "ok1.example.com", "employee_count": 42.0, "summary_zh": "详情补的中文描述"}}}
            out = Path(tmp) / "tmp-r2-src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 0, p.stderr)
            r0 = json.loads(out.read_text(encoding="utf-8"))["rows"][0]
            self.assertEqual(r0["company_name"], "未知")
            self.assertEqual(r0["country_code"], "未知")
            self.assertEqual(r0["size"], "42")
            self.assertEqual(r0["summary_zh"], "详情补的中文描述")

    def test_bad_page_rejected_before_any_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _b = self._setup(tmp)
            out = Path(tmp) / "tmp-r2-src.json"
            for bad in ("abc", "0", "-1", "1.5", " 2x"):
                p = self._collect(ctx, out, page=bad)
                self.assertEqual(p.returncode, 2, bad)
                self.assertIn("--page", p.stderr)
                self.assertNotIn("Traceback", p.stderr)
            self.assertEqual(_R2Handler.state["paths"], [])

    def test_zero_rows_and_unknown_total_reported_as_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _b = self._setup(tmp)
            _R2Handler.state["list_resp"] = lambda x: {"success": True, "data": {"list": [], "total": "abc"}}
            out = Path(tmp) / "tmp-r2-src.json"
            p = self._collect(ctx, out)
            self.assertEqual(p.returncode, 0, p.stderr)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(doc["row_count"], 0)
            self.assertEqual(doc["platform_total"], "unknown")
            p2, md = self._render(tmp, out, {"source_sha256": doc["source_sha256"], "judgments": []})
            self.assertEqual(p2.returncode, 0, p2.stderr)
            self.assertIn("0 家", md)
            self.assertIn("没有可靠推荐", md)


class R3CompanyPageReportTest(unittest.TestCase):
    """R3：所有存在且非空的 id/company_id/_id 逐一与原 cid 比对，任何矛盾即 id_mismatch。"""

    def _setup(self, tmp):
        _R2Handler.state = {"paths": [], "list_bodies": [], "details": {},
                            "list_resp": lambda b: {"success": True, "data": {"list": [], "total": 0}}}
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _R2Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        ctx = Path(tmp) / "r3ctx.json"
        ctx.write_text(json.dumps({"base_url": "http://127.0.0.1:%d" % srv.server_address[1]}),
                       encoding="utf-8")
        return ctx

    def _collect(self, ctx, out):
        return _run(["collect", "--keyword", KEYWORD, "--page", "1", "--credentials-stdin",
                     "--api-context", str(ctx), "--out", str(out)],
                    stdin="token=%s\norg=%s\n" % (TOKEN, ORG))

    def _one(self, tmp, detail_extra, expect_status, expect_url=""):
        ctx = self._setup(tmp)
        _R2Handler.state["list_resp"] = lambda b: {"success": True, "data": {"list": [_lrow(1)], "total": 1}}
        data = {"domain": "alias1.example.com"}
        data.update(detail_extra)
        _R2Handler.state["details"] = {IDS[0]: {"success": True, "data": data}}
        out = Path(tmp) / "tmp-r3-src.json"
        p = self._collect(ctx, out)
        self.assertEqual(p.returncode, 0, p.stderr)
        row = json.loads(out.read_text(encoding="utf-8"))["rows"][0]
        self.assertEqual(row["detail_status"], expect_status)
        self.assertEqual(row["url"], expect_url)
        self.assertEqual(row["domain"], expect_url.replace("https://", ""))
        return row

    def test_id_ok_but_company_and_underscore_mismatch(self):
        """安全席真反例：id=orig 但 company_id=other、_id=third → 不得仍 ok 挂错网址。"""
        with tempfile.TemporaryDirectory() as tmp:
            row = self._one(tmp, {"id": IDS[0], "company_id": "a" * 32, "_id": "b" * 32},
                            "id_mismatch")
            self.assertEqual(row["summary_zh"], "第1家：专注宠物食品与用品批发分销，覆盖连锁零售渠道。")
            self.assertNotIn("wrong", row["domain"])

    def test_order_swapped_aliases_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._one(tmp, {"company_id": IDS[0], "id": "c" * 32}, "id_mismatch")

    def test_all_aliases_equal_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._one(tmp, {"id": IDS[0], "company_id": IDS[0], "_id": IDS[0]}, "ok",
                      "https://alias1.example.com")

    def test_no_identity_fields_keeps_normal_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._one(tmp, {}, "ok", "https://alias1.example.com")

    def test_non_string_alias_type_is_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._one(tmp, {"id": {"nested": 1}}, "id_mismatch")


if __name__ == "__main__":
    unittest.main()
