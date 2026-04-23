import { createRuntimeFromEnv } from "./bootstrap/create-runtime-from-env.js";
import { createAppServer } from "./interfaces/http/create-app-server.js";

const runtime = await createRuntimeFromEnv();
const server = createAppServer(runtime);
const port = Number(process.env.PORT ?? 3000);

server.listen(port, "0.0.0.0", () => {
  process.stdout.write(`membermanagement-rewrite listening on http://0.0.0.0:${port}\n`);
});
