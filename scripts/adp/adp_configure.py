"""Configure the ADP app as RydeResolve's official-policy assistant.

Backs up the current config to adp_config_backup.json first (only on the first run),
then changes only: model (Tencent Hunyuan Hy3, low temperature), role description,
greeting, opening questions, answer-only-from-knowledge-base, doc retrieval depth.
    python adp_configure.py            # apply
    python adp_configure.py --restore  # put the backed-up config back
"""
import json
import sys
from pathlib import Path

from adp_common import client, models, the_app

HERE = Path(__file__).parent
BACKUP = HERE / "adp_config_backup.json"  # holds no keys; gitignore-safe

ROLE = """You are the RydeResolve Policy Assistant for Ryde, a ride-hailing platform in Singapore.
Your knowledge base holds Ryde's official policies, copied word for word from help.rydesharing.com and rydesharing.com.

Rules:
1. Answer ONLY from the knowledge base. If the official policy does not cover the question, say "The official Ryde policy does not state this." Never guess or use outside knowledge.
2. Quote exact amounts, time limits and conditions as written (for example "S$6.61", "within 3 minutes of matching", "within 30 days").
3. Name the source article or clause and its last-updated date for every rule you use.
4. Rider and driver articles can state different amounts for the same fee (the rider pays S$6.61, the driver receives S$4.50). Say which side each amount applies to.
5. Be concise and neutral. You explain policy; you do not decide disputes.
Reply in the language of the question."""

GREETING = ("Hi, I'm the RydeResolve Policy Assistant. Ask me about Ryde's official rules on cancellation and "
            "waiting fees, fares, ERP, cleaning claims, ratings or safety. Every answer cites the official source.")

OPENING = [
    "How much is the cancellation fee if I cancel after 3 minutes?",
    "When can a driver charge a no-show fee?",
    "What evidence does a driver need for a cleaning claim?",
]


def current_config(app_id: str) -> dict:
    req = models.DescribeAppRequest()
    req.AppBizId = app_id
    return json.loads(client.DescribeApp(req).to_json_string())


def modify(app, app_config: dict, base: dict | None = None):
    req = models.ModifyAppRequest()
    payload = {"AppBizId": app.AppBizId, "AppType": app.AppType, "AppConfig": app_config}
    if base:
        payload["BaseConfig"] = base
    req.from_json_string(json.dumps(payload))
    client.ModifyApp(req)


def main():
    app = the_app()
    cfg = current_config(app.AppBizId)
    if "--restore" in sys.argv:
        saved = json.loads(BACKUP.read_text(encoding="utf-8"))
        modify(app, saved["AppConfig"], saved["BaseConfig"])
        print("restored the backed-up config")
        return
    if not BACKUP.exists():
        BACKUP.write_text(json.dumps({"AppConfig": cfg["AppConfig"], "BaseConfig": cfg["BaseConfig"]},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"backup written: {BACKUP.name}")

    qa = cfg["AppConfig"]["KnowledgeQa"]
    qa["RoleDescription"] = ROLE
    qa["Greeting"] = GREETING
    qa["OpeningQuestions"] = OPENING
    model = qa["Model"]
    model.update({"Name": "Hunyuan/hy3", "AliasName": "Tencent Hy3"})
    model.setdefault("ModelParams", {})["Temperature"] = 0.1
    model["ModelParams"]["DeepThinking"] = "disabled"
    qa["Output"]["UseGeneralKnowledge"] = False  # policy answers must come from the knowledge base
    # "agent" mode lets the model skip retrieval (it asked "which platform?" instead of
    # searching); standard mode always retrieves from the knowledge base first
    qa["Pattern"] = "standard"
    for s in qa["Search"]:
        if s["Type"] == "doc":
            s["DocTopN"] = 8  # a question can touch both the rider and the driver article
    modify(app, cfg["AppConfig"], cfg["BaseConfig"])  # BaseConfig is required; sent back unchanged

    after = current_config(app.AppBizId)["AppConfig"]["KnowledgeQa"]
    print("model:", after["Model"]["Name"], "| temperature:", after["Model"].get("ModelParams", {}).get("Temperature"))
    print("general knowledge:", after["Output"]["UseGeneralKnowledge"],
          "| doc top-n:", [s["DocTopN"] for s in after["Search"] if s["Type"] == "doc"])
    print("role set:", after.get("RoleDescription", "")[:60], "...")
    print("opening questions:", len(after.get("OpeningQuestions") or []))


if __name__ == "__main__":
    main()
