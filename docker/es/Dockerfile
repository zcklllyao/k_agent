# 基于官方 ES 8.17.0 安装 IK 中文分词插件
FROM docker.elastic.co/elasticsearch/elasticsearch:8.17.0

# analysis-ik 版本需与 ES 版本严格一致
RUN bin/elasticsearch-plugin install --batch \
    https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-8.17.0.zip
