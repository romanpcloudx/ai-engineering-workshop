import util from "node:util";

function contentText(item) {
  if (typeof item.content === "string") return item.content;
  if (Array.isArray(item.content)) {
    return item.content
      .map((content) => content.text)
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

function historyLine(index, item) {
  if (item.type === "reasoning") {
    const summaries = item.summary
      ?.map((summary) => summary.text)
      .filter(Boolean)
      .join("\n");
    const detail = summaries || "encrypted reasoning item";
    return `${index}. reasoning: ${detail}`;
  }

  if (item.type === "function_call") {
    return `${index}. function_call: ${item.name}(${item.arguments}) call_id=${item.call_id}`;
  }

  if (item.type === "function_call_output") {
    return `${index}. function_call_output: call_id=${item.call_id} output=${item.output}`;
  }

  return `${index}. ${item.role}: ${contentText(item)}`;
}

export function logHistory(history) {
  console.log("\x1b[34m[history sent to openai]\x1b[0m");
  for (const [index, item] of history.entries()) {
    console.log(historyLine(index, item));
  }
  console.log("\x1b[34m[/history sent to openai]\x1b[0m");
}

export function logOpenAIResponse(response) {
  console.log("\x1b[35m[openai response]\x1b[0m");
  console.log(
    util.inspect(
      {
        id: response.id,
        status: response.status,
        model: response.model,
        output: response.output,
        output_text: response.output_text,
        usage: response.usage,
      },
      { depth: null, colors: false },
    ),
  );
  console.log("\x1b[35m[/openai response]\x1b[0m");
}
