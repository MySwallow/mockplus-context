# Examples

## 1. 还原单页 UI

```bash
# 1. 拿结构化 JSON
mockplus get-data 'https://app.mockplus.cn/app/5gAIPn9LE/develop/design/0-ITsFIbmL' > page.json

# 2. 在 page.json 里找 asset.url(切图),也找 metadata.pageImage.url(整页图)
jq '.nodes | .. | objects | select(.asset) | .asset.url' page.json

# 3. 让 LLM 决定要哪些切图,起语义化文件名,下载
mockplus download-assets \
  --downloads '[
    {"url":"https://img02.mockplus.cn/idoc/sketch/abc.../...png","fileName":"nav-back.png"},
    {"url":"https://img02.mockplus.cn/idoc/sketch/def.../...png","fileName":"submit-icon.png"}
  ]' \
  --local-path ./assets
```

## 2. 批量浏览一个分组

```bash
# 看项目结构(text 或 json 格式都可)
mockplus tree 5gAIPn9LE
# 或解析 JSON 拿到具体 page id 列表:
mockplus tree 5gAIPn9LE --format json | \
  jq -r '.. | objects | select(.kind=="page") | .id'

# 决定要某几页之后,循环 get-data
for pid in p-001 p-002 p-003; do
  mockplus get-data 5gAIPn9LE:$pid > pages/$pid.json
done
```

## 3. 检测 Mockplus 是否升级了 schema

```bash
mockplus inspect 5gAIPn9LE:0-ITsFIbmL | jq '._meta.unhandledFields // empty'
# 空 → schema 没变
# 非空 → 有新字段没消费,需要更新 _transform.py
```

## 4. CI 中用

```bash
export MOCKPLUS_COOKIE='<from secret>'
mockplus cookie test $APP_ID || exit 1
mockplus get-data $URL > artifact.json
```

环境变量优先于文件,适合无状态 CI。
