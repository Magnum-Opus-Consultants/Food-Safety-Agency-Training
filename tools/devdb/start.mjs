// Starts a local PostgreSQL for development and keeps it running until Ctrl+C.
// Data lives in ./data so whatever you capture survives a restart.
// Production uses a managed PostgreSQL; this is only for developer machines.
import EmbeddedPostgres from 'embedded-postgres';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const databaseDir = path.join(here, 'data');
const port = Number(process.env.DEVDB_PORT || 5433);

const pg = new EmbeddedPostgres({
  databaseDir,
  user: 'fsa',
  password: 'fsa',
  port,
  persistent: true,
  initdbFlags: ['--encoding=UTF8', '--locale=C'],
  onLog: () => {},
});

const fresh = !existsSync(path.join(databaseDir, 'PG_VERSION'));
if (fresh) await pg.initialise();
await pg.start();

const client = pg.getPgClient();
await client.connect();
const { rows } = await client.query("SELECT 1 FROM pg_database WHERE datname = 'fsa_training'");
if (rows.length === 0) await client.query("CREATE DATABASE fsa_training ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0");
await client.end();

console.log(`PostgreSQL ready on localhost:${port} (database fsa_training, user fsa / fsa). Ctrl+C to stop.`);

const stop = async () => { await pg.stop(); process.exit(0); };
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
setInterval(() => {}, 1 << 30);
