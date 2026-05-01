# Netlify Deployment Guide

## Step 1: Prepare Frontend

1. Ensure your frontend builds successfully:
   ```bash
   cd frontend
   npm install
   npm run build
   ```

2. Copy `.env.example` to `.env.local` and set your API URL:
   ```bash
   cp frontend/.env.example frontend/.env.local
   ```

3. Update `frontend/vite.config.js` to use environment variables:
   ```javascript
   server: {
     proxy: {
       '/api': {
         target: import.meta.env.VITE_API_URL || 'http://localhost:8000',
         changeOrigin: true
       }
     }
   }
   ```

## Step 2: Deploy Backend First

**Choose ONE of these options:**

### Option A: Heroku (Free tier deprecated, but you can use Paid)
```bash
heroku create your-app-name
git push heroku main
heroku config:set GROQ_API_KEY=your_key
heroku config:set GROQ_MODEL=llama-3.3-70b-versatile
heroku open
```

### Option B: Render (Recommended)
1. Go to [render.com](https://render.com)
2. Create new "Web Service"
3. Connect your GitHub repo
4. Set Build Command: `pip install -r backend/requirements.txt`
5. Set Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
6. Add Environment Variables:
   - `GROQ_API_KEY`: Your Groq API key
   - `GROQ_MODEL`: llama-3.3-70b-versatile
7. Deploy

### Option C: Railway
1. Go to [railway.app](https://railway.app)
2. Create new project, connect GitHub
3. Railway auto-detects Python and deploys with `main.py`
4. Add env vars for GROQ_API_KEY
5. Deploy

### Option D: Fly.io
1. Install Fly CLI
2. Run `flyctl launch` in backend directory
3. Add env vars and deploy

## Step 3: Deploy Frontend to Netlify

### Method 1: GitHub Integration (Recommended)
1. Push your code to GitHub
2. Go to [netlify.com](https://netlify.com) → Sign up/Login
3. Click "Add new site" → "Import an existing project"
4. Select GitHub and choose your repository
5. Set Build Command: `cd frontend && npm install && npm run build`
6. Set Publish Directory: `frontend/dist`
7. Click Deploy

### Method 2: Drag & Drop
1. Build locally:
   ```bash
   cd frontend && npm run build
   ```
2. Drag `frontend/dist` folder into Netlify dashboard

## Step 4: Configure Environment Variables in Netlify

1. Go to Netlify Site Settings → Build & Deploy → Environment
2. Add variable:
   - Key: `VITE_API_URL`
   - Value: `https://your-backend-url.com` (your Render/Railway/Fly.io URL)

## Step 5: Update API Proxy Configuration

Update `frontend/src/main.jsx` or create an API client to use the correct backend:

```javascript
const API_URL = import.meta.env.VITE_API_URL || process.env.REACT_APP_API_URL || 'http://localhost:8000';

export const apiClient = {
  async post(endpoint, data) {
    const response = await fetch(`${API_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    return response.json();
  },
  
  async get(endpoint) {
    const response = await fetch(`${API_URL}${endpoint}`);
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    return response.json();
  },
};
```

## Troubleshooting

### CORS Errors
Backend should have proper CORS configuration:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-netlify-site.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Build Failures
- Check build logs in Netlify dashboard
- Ensure `npm run build` works locally
- Verify all dependencies are in `package.json`

### 404 on SPA Routes
This is already handled by the `netlify.toml` redirect rule - it will route all non-API requests to `index.html` for React Router.

## Production Checklist

- [ ] Backend deployed and running
- [ ] Frontend builds successfully locally
- [ ] Environment variables set in Netlify
- [ ] CORS configured in backend
- [ ] API URL correctly set in frontend env vars
- [ ] Test API calls work from frontend
- [ ] Monitor backend logs for errors
