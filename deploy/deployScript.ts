import { readFileSync } from "fs";
import path from "path";
import { TransactionHash, TransactionStatus } from "genlayer-js/types";
import { localnet } from "genlayer-js/chains";

export default async function main(client) {
  const filePath = path.resolve(process.cwd(), "contracts/bounty_court.py");
  const contractCode = new Uint8Array(readFileSync(filePath));

  await client.initializeConsensusSmartContract();

  const deployTransaction = await client.deployContract({ code: contractCode, args: [] });

  const receipt = await client.waitForTransactionReceipt({
    hash: deployTransaction,
    status: TransactionStatus.ACCEPTED,
    retries: 200,
  });

  if (
    receipt.status !== 5 &&
    receipt.status !== 6 &&
    receipt.statusName !== "ACCEPTED" &&
    receipt.statusName !== "FINALIZED"
  ) {
    throw new Error("Deployment failed. Receipt: " + JSON.stringify(receipt));
  }

  const address =
    client.chain.id === localnet.id
      ? receipt.data.contract_address
      : receipt.txDataDecoded?.contractAddress;

  console.log("Contract deployed at address: " + address);
}
