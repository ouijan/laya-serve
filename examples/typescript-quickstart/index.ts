import {
	type Answer,
	createLayaClient,
	isChoice,
	isNoul,
	isScore,
} from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://localhost:11500" });

// Edit this: the situation you want decided.
const state =
	"We were billed twice for March and nobody has replied in 3 days. If this is not fixed we will move to a competitor.";

// Edit these: every question is answered in the same forward pass.
const { answers, routing, usage } = await laya.systemOne({
	state,
	questions: {
		department: {
			type: "choice",
			instructions: "Which team should handle this?",
			criteria: {
				billing: "payments, refunds, invoices",
				technical: "bugs and integrations",
				sales: "pricing and accounts",
			},
		},
		frustration: {
			type: "score",
			instructions: "How frustrated the customer appears",
			criteria: ["Calm", "Frustrated but civil", "Very angry"],
		},
		churn_risk: {
			type: "noul",
			instructions: "The customer threatens to leave",
		},
	},
});

/** `answers` is a union discriminated on `type`; narrow it and the fields follow. */
function describe(answer: Answer): string {
	if (isChoice(answer)) return answer.choice;
	if (isScore(answer)) return answer.score.toFixed(2);
	if (isNoul(answer)) return answer.noul.toFixed(4);
	return "unknown answer type";
}

for (const [id, answer] of Object.entries(answers)) {
	const confidence = answer.confidence.toFixed(2);
	console.log(`${id.padEnd(12)} ${describe(answer)}  (confidence ${confidence})`);
}

console.log(`\nanswered by ${routing?.model}: ${routing?.reason}`);
console.log(`${usage.input_tokens} input tokens in, ${usage.output_tokens} out`);
