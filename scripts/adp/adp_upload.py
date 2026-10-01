"""Upload official Ryde policy .md files into the ADP app's knowledge base.

    python adp_upload.py <file.md> [<file.md> ...]

Per file: ADP issues a temporary COS credential -> the file goes to COS -> SaveDoc
registers it in the knowledge base. Files already in the knowledge base (same name)
are skipped so re-running never creates duplicates."""
import json
import sys
from pathlib import Path

from qcloud_cos import CosConfig, CosS3Client

from adp_common import client, models, the_app

app = the_app()
bot = app.AppBizId

listing = models.ListDocRequest()
listing.BotBizId, listing.PageNumber, listing.PageSize = bot, 1, 200
existing = {d.FileName for d in (client.ListDoc(listing).List or [])}

for arg in sys.argv[1:]:
    path = Path(arg)
    if path.name in existing:
        print(f"skip (already in KB): {path.name}")
        continue
    data = path.read_bytes()

    cred_req = models.DescribeStorageCredentialRequest()
    cred_req.BotBizId, cred_req.FileType, cred_req.IsPublic = bot, "md", False
    cred = client.DescribeStorageCredential(cred_req)

    cos = CosS3Client(CosConfig(
        Region=cred.Region,
        SecretId=cred.Credentials.TmpSecretId,
        SecretKey=cred.Credentials.TmpSecretKey,
        Token=cred.Credentials.Token,
        Scheme="https",
    ))
    put = cos.put_object(Bucket=cred.Bucket, Key=cred.UploadPath, Body=data)

    save = models.SaveDocRequest()
    save.BotBizId = bot
    save.FileName = path.name
    save.FileType = "md"
    save.CosUrl = cred.UploadPath
    save.ETag = put.get("ETag", "")
    save.CosHash = put.get("x-cos-hash-crc64ecma", "")
    save.Size = str(len(data))
    save.AttrRange = 1   # visible to every label/scope
    save.Opt = 2         # normal document import
    save.Source = 0      # uploaded file
    save.IsRefer = True  # answers may cite this document
    save.EnableScope = 4  # default 2 = development only: the published app would not see it
    resp = client.SaveDoc(save)
    print(f"saved: {path.name}  DocBizId={resp.DocBizId}  {resp.ErrorMsg or ''}")
