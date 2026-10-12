FROM busybox:1.37.0 AS healthcheck

FROM mockserver/mockserver:8.0.0

COPY --from=healthcheck /bin/busybox /bin/busybox
COPY analysis-provider-initialization.json /config/analysis-provider-initialization.json
