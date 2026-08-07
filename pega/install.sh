cp pega/distr/archives/prweb.war pega/application/
docker compose up --exit-code-from pega-installer pega-installer
docker compose rm -fs pega-installer
