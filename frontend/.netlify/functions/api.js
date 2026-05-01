// This file proxies API requests to your backend server
// Update BACKEND_URL to your deployed Python backend URL

const BACKEND_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

exports.handler = async (event, context) => {
  const path = event.path.replace("/.netlify/functions/api", "");
  
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: event.httpMethod,
      headers: {
        ...event.headers,
        "Content-Type": "application/json",
      },
      body: event.body,
    });

    return {
      statusCode: response.status,
      body: await response.text(),
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
      },
    };
  } catch (error) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: error.message }),
    };
  }
};
