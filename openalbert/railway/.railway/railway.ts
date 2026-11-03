// Secrets stay in Railway. The native bucket was deployed through the dashboard.
// Keep its declaration here so future infrastructure changes preserve it.
import { bucket, defineRailway, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const files = bucket("openalbert-files", { region: "ams" });
  const Postgres = postgres("Postgres", { region: "europe-west4" });
  Postgres.networking = { privateNetworkEndpoint: "postgres-50bfa805" };
  const albertData = volume("albert-data", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 1024 });
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 5000 });
  const computerData = volume("computer-data", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 4096 });
  const computer = service("computer", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    replicas: { "europe-west4": 1 },
    deploy: { drainingSeconds: 45, overlapSeconds: 0 },
    volumeMounts: { "/data": computerData },
    env: { COMPUTER_AUTHORIZED_KEY: preserve(), RAILWAY_RUN_UID: preserve() },
  });
  const temporal = service("temporal", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    replicas: { "europe-west4": 1 },
    deploy: { drainingSeconds: 45, overlapSeconds: 0 },
    env: { BIND_ON_IP: preserve(), DB: preserve(), DBNAME: preserve(), DB_PORT: Postgres.env.PGPORT, DEFAULT_NAMESPACE: preserve(), DYNAMIC_CONFIG_FILE_PATH: preserve(), LOG_LEVEL: preserve(), POSTGRES_PWD: Postgres.env.PGPASSWORD, POSTGRES_SEEDS: Postgres.env.PGHOST, POSTGRES_USER: Postgres.env.PGUSER, SKIP_DB_CREATE: "false", TEMPORAL_ADDRESS: preserve(), TEMPORAL_CLI_ADDRESS: preserve(), VISIBILITY_DBNAME: preserve() },
  });
  const openalbert = service("openalbert", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/healthz",
    healthcheckTimeout: 180,
    replicas: { "europe-west4": 1 },
    deploy: { drainingSeconds: 45, overlapSeconds: 0 },
    volumeMounts: { "/data": albertData },
    env: { BACKUP_STATE_DIR: preserve(), BROWSER_ENABLED: preserve(), BROWSER_NO_SANDBOX: preserve(), COMPUTER_SSH_ADDRESS: "${{computer.RAILWAY_PRIVATE_DOMAIN}}:22", COMPUTER_SSH_KEY_FILE: preserve(), COMPUTER_SSH_PRIVATE_KEY: preserve(), COMPUTER_SSH_USER: preserve(), DATABASE_URL: Postgres.env.DATABASE_URL, HTTP_ADDR: preserve(), INSPECTOR_PUBLIC_URL: preserve(), KNOWLEDGE_DIR: preserve(), LLM_API_KEY: preserve(), LLM_BASE_URL: preserve(), LLM_MODEL: preserve(), PORT: preserve(), RAILWAY_RUN_UID: preserve(), RAILWAY_SHM_SIZE_BYTES: preserve(), S3_ACCESS_KEY: "${{openalbert-files.ACCESS_KEY_ID}}", S3_BUCKET: "${{openalbert-files.BUCKET}}", S3_ENDPOINT: "t3.storageapi.dev", S3_SECRET_KEY: "${{openalbert-files.SECRET_ACCESS_KEY}}", S3_SECURE: "true", STT_API_KEY: "", STT_BASE_URL: "", STT_MODEL: "", STT_REVISION: "", TELEGRAM_ALLOWED_GROUP_IDS: preserve(), TELEGRAM_ALLOW_BOT_MESSAGES: "true", TELEGRAM_ALLOWED_USER_IDS: preserve(), TELEGRAM_BOT_TOKEN: preserve(), TELEGRAM_OWNER_USER_ID: preserve(), TEMPORAL_ADDRESS: "${{temporal.RAILWAY_PRIVATE_DOMAIN}}:7233", TEMPORAL_NAMESPACE: preserve(), TEMPORAL_TASK_QUEUE: preserve(), VICTORIALOGS_URL: preserve() },
  });

  return project("openalbert-no-stt", {
    variables: { managed: true },
    resources: [files, Postgres, computer, temporal, openalbert, albertData, postgresVolume, computerData],
  });
});
