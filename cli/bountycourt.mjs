#!/usr/bin/env node
/**
 * bountycourt — CLI for the BountyCourt intelligent contract.
 *
 * Every command is a thin wrapper around one contract call. There is no server
 * and no database: the verdict lives on GenLayer, the CLI only asks for it.
 *
 *   node cli/bountycourt.mjs create --title "..." --rubric-file rubric.md --deadline 2026-10-30 --min 60
 *   node cli/bountycourt.mjs submit --bounty b0 --url https://... --note "second pass"
 *   node cli/bountycourt.mjs judge  --submission s0
 *   node cli/bountycourt.mjs show   --bounty b0
 *   node cli/bountycourt.mjs list   --bounty b0
 *   node cli/bountycourt.mjs stats
 */
import { readFileSync } from "node:fs";
import { createClient } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { privateKeyToAccount } from "viem/accounts";

const NETWORKS = { bradbury: testnetBradbury };

function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token.startsWith("--")) {
      const key = token.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) out[key] = true;
      else {
        out[key] = next;
        i += 1;
      }
    } else out._.push(token);
  }
  return out;
}

function env(name, fallback) {
  const v = process.env[name];
  return v === undefined || v === "" ? fallback : v;
}

function makeClient() {
  const chain = NETWORKS[env("BOUNTYCOURT_NETWORK", "bradbury")];
  if (!chain) throw new Error("Unknown BOUNTYCOURT_NETWORK");
  const pk = env("BOUNTYCOURT_PRIVATE_KEY", "");
  const config = { chain };
  if (pk) config.account = privateKeyToAccount(pk);
  return createClient(config);
}

function contractAddress() {
  const address = env("BOUNTYCOURT_ADDRESS", "");
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) {
    throw new Error("Set BOUNTYCOURT_ADDRESS to the deployed contract address");
  }
  return address;
}

async function read(client, functionName, args) {
  return client.readContract({
    address: contractAddress(),
    functionName,
    args,
  });
}

async function write(client, functionName, args, value) {
  const payload = { address: contractAddress(), functionName, args };
  if (value !== undefined) payload.value = value;
  const hash = await client.writeContract(payload);
  const receipt = await client.waitForTransactionReceipt({ hash });
  return receipt;
}

function print(value) {
  process.stdout.write(JSON.stringify(value, null, 2) + "\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cmd = args._[0];
  const client = makeClient();

  switch (cmd) {
    case "create": {
      const rubricFile = args["rubric-file"];
      if (!rubricFile) throw new Error("--rubric-file is required");
      const rubric = readFileSync(rubricFile, "utf8").trim();
      const receipt = await write(client, "create_bounty", [
        String(args.title ?? ""),
        rubric,
        String(args.deadline ?? ""),
        Number(args.min ?? 60),
      ]);
      print({ status: receipt?.statusName ?? receipt?.status, receipt });
      break;
    }
    case "submit": {
      const receipt = await write(client, "submit_deliverable", [
        String(args.bounty ?? ""),
        String(args.url ?? ""),
        String(args.note ?? ""),
      ]);
      print({ status: receipt?.statusName ?? receipt?.status, receipt });
      break;
    }
    case "judge": {
      const receipt = await write(client, "adjudicate", [String(args.submission ?? "")]);
      print({ status: receipt?.statusName ?? receipt?.status, receipt });
      print(await read(client, "get_submission", [String(args.submission ?? "")]));
      break;
    }
    case "show": {
      print(await read(client, "get_bounty", [String(args.bounty ?? "")]));
      break;
    }
    case "list": {
      const ids = await read(client, "list_submissions", [String(args.bounty ?? "")]);
      const rows = [];
      for (const id of ids) rows.push(await read(client, "get_submission", [id]));
      print(rows);
      break;
    }
    case "stats": {
      print(await read(client, "stats", []));
      break;
    }
    default:
      process.stderr.write(
        "usage: bountycourt <create|submit|judge|show|list|stats> [--flags]\n"
      );
      process.exitCode = 1;
  }
}

main().catch((err) => {
  process.stderr.write(String(err?.message ?? err) + "\n");
  process.exitCode = 1;
});
