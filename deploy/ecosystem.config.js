/**
 * PM2 ecosystem config untuk Stock Intelligence API
 * Jalankan: pm2 start ecosystem.config.js
 * Restart: pm2 restart stock-api
 * Log: pm2 logs stock-api
 */

module.exports = {
  apps: [
    {
      name: "stock-api",
      script: "/opt/stock-intelligence/venv/bin/uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8000 --workers 2 --loop uvloop",
      cwd: "/opt/stock-intelligence/api",
      interpreter: "none",

      // Environment — JANGAN simpan secret di sini, gunakan .env file
      env: {
        PYTHONPATH: "/opt/stock-intelligence/api",
        APP_ENV: "production",
        LOG_LEVEL: "INFO",
      },

      // Restart policy
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
      restart_delay: 5000,

      // Log
      log_file: "/opt/stock-intelligence/logs/stock-api.log",
      error_file: "/opt/stock-intelligence/logs/stock-api-error.log",
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",

      // Graceful shutdown
      kill_timeout: 10000,
      listen_timeout: 8000,
    },
  ],
};
