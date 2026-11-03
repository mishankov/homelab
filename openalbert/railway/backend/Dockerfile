FROM ghcr.io/mishankov/openalbert/openalbert@sha256:cae81fcf10416be3f022b850bc79262b132d59ebf5ce660bb0d7fda0d2632b36
USER root
RUN apk add --no-cache su-exec openssh-client-default
COPY entrypoint.sh /usr/local/bin/railway-entrypoint
RUN chmod 0755 /usr/local/bin/railway-entrypoint
ENTRYPOINT ["/usr/local/bin/railway-entrypoint"]
