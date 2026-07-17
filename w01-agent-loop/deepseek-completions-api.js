#!/usr/bin/env node
// 01 - Agent loop with one tool: get_weather(city).

import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import OpenAI from "openai";
import dotenv from "dotenv";

dotenv.config({ override: true, quiet: true });

const client = new OpenAI({
    baseURL: "https://api.deepseek.com",
    apiKey: process.env.DEEPSEEK_API_KEY,
});
const MODEL = "deepseek-v4-pro";

const SYSTEM =
  "You are a helpful assistant.";

const TOOLS = [
  {
    type: "function",
    function: {
        name: "get_weather",
        strict: true,
        description: "Get the current weather for a city using OpenWeatherMap.",
        parameters: {
          type: "object",
          properties: {
            city: {
              type: "string",
              description: "City name, optionally with country code. Example: Buenos Aires,AR",
            },
          },
          required: ["city"],
          additionalProperties: false,
        },
    },
  },
];

async function getWeather(city) {
  const apiKey = process.env.OPENWEATHER_KEY;
  if (!apiKey) {
    return "Error: OPENWEATHER_KEY is not configured.";
  }

  const url = new URL("https://api.openweathermap.org/data/2.5/weather");
  url.searchParams.set("q", city);
  url.searchParams.set("appid", apiKey);
  url.searchParams.set("units", "metric");
  url.searchParams.set("lang", "es");

  const response = await fetch(url);
  const data = await response.json();

  if (!response.ok) {
    return `Error: OpenWeatherMap returned ${response.status}: ${
      data.message ?? "unknown error"
    }`;
  }

  return JSON.stringify({
    city: data.name,
    country: data.sys?.country,
    description: data.weather?.[0]?.description,
    temperature_c: data.main?.temp,
    feels_like_c: data.main?.feels_like,
    humidity_percent: data.main?.humidity,
    wind_speed_mps: data.wind?.speed,
  });
}

async function runTool(toolCall) {
  const { name, arguments: args } = toolCall.function;

  if (name !== "get_weather") {
    return `Error: Unknown tool "${name}".`;
  }

  try {
    const { city } = JSON.parse(args);
    console.log(`\x1b[33mget_weather city=${city}\x1b[0m`);
    const result = await getWeather(city);
    console.log(result);
    return result;
  } catch (err) {
    return `Error: Invalid tool arguments: ${err.message}`;
  }
}

async function agentLoop(history) {
  while (true) {
    console.log('history', history);

    const response = await client.chat.completions.create({
      model: MODEL,
      thinking: { type: "enabled" },
      reasoning_effort: "high",
      messages: history,
      tools: TOOLS,
      max_tokens: 8000,
    });

    const message = response.choices[0].message;
    console.log('message', message);
    history.push(message);

    const toolCalls = message.tool_calls;
    if (!toolCalls?.length) {
      return message.content;
    }

    for (const toolCall of toolCalls) {
      const toolOutput = await runTool(toolCall);
      history.push({
        role: "tool",
        tool_call_id: toolCall.id,
        content: toolOutput,
      });
    }
  }
}

const rl = readline.createInterface({ input, output });
const history = [{ role: "system", content: SYSTEM }];

while (true) {
  let query;
  try {
    query = await rl.question("\x1b[36ms01 >> \x1b[0m");
  } catch {
    break;
  }

  if (["q", "exit", ""].includes(query.trim().toLowerCase())) {
    break;
  }

  history.push({ role: "user", content: query });
  const answer = await agentLoop(history);
  if (answer) console.log(answer);
  console.log();
}

rl.close();
