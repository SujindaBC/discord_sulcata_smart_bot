from fastapi import FastAPI, Request, HTTPException
import matplotlib.pyplot as plt
from io import BytesIO
import pandas as pd
import discord
from discord.ext import commands
import asyncio
from dotenv import load_dotenv
import os
import logging
from datetime import datetime, timedelta
import json
from typing import List, Dict, Any, Optional
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    logger.error("DISCORD_TOKEN not found in environment variables")
    raise EnvironmentError("DISCORD_TOKEN not found in environment variables")

# Load alert channel ID if available
ALERT_CHANNEL_ID = os.getenv("ALERT_CHANNEL_ID")
if ALERT_CHANNEL_ID:
    try:
        ALERT_CHANNEL_ID = int(ALERT_CHANNEL_ID)
        logger.info(f"Alert channel ID set to: {ALERT_CHANNEL_ID}")
    except ValueError:
        logger.error("Invalid ALERT_CHANNEL_ID format. Must be an integer.")
        ALERT_CHANNEL_ID = None
else:
    logger.warning("ALERT_CHANNEL_ID not set. Alerts will not be sent automatically.")

# Data storage path
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "sensor_data.json")

# Create data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)

# FastAPI app
app = FastAPI(title="Weather Station API")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix="!", intents=intents)

# Maximum number of data points to store in memory
MAX_DATA_POINTS = 10000

# Store sensor data
sensor_data: List[Dict[str, Any]] = []

# Sulcata tortoise environmental parameters
SULCATA_ENV = {
    "temp_min": 18.0,       # Minimum safe temperature in Celsius (65°F)
    "temp_ideal_min": 27.0, # Ideal minimum temperature in Celsius (80°F)
    "temp_ideal_max": 35.0, # Ideal maximum temperature in Celsius (95°F)
    "temp_max": 40.0,       # Maximum safe temperature in Celsius (104°F)
    "hum_min": 40.0,        # Minimum humidity percentage
    "hum_max": 60.0,        # Maximum humidity percentage
}

# Alert settings
ALERT_CHANNEL_ID = None  # Will be set from environment variable
last_alert_time = 0
ALERT_COOLDOWN = 1800  # 30 minutes cooldown between alerts

# --- Data Management Functions ---

def load_sensor_data() -> None:
    """Load sensor data from file if it exists"""
    global sensor_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as file:
                data = json.load(file)
                # Convert string time back to pandas Timestamp
                for entry in data:
                    entry["time"] = pd.Timestamp(entry["time"])
                sensor_data = data[-MAX_DATA_POINTS:]  # Keep only the latest MAX_DATA_POINTS
                logger.info(f"Loaded {len(sensor_data)} data points from file")
    except Exception as e:
        logger.error(f"Error loading sensor data: {e}")
        sensor_data = []

def save_sensor_data() -> None:
    """Save sensor data to file"""
    try:
        # Convert pd.Timestamp to string for JSON serialization
        data_to_save = [
            {**item, "time": item["time"].isoformat()} 
            for item in sensor_data
        ]
        with open(DATA_FILE, 'w') as file:
            json.dump(data_to_save, file)
        logger.info(f"Saved {len(data_to_save)} data points to file")
    except Exception as e:
        logger.error(f"Error saving sensor data: {e}")

# --- Discord Bot Commands ---

@bot.event
async def on_ready():
    """Event triggered when the bot is ready"""
    logger.info(f"Bot connected as {bot.user}")
    
    # Check if alert channel exists
    if ALERT_CHANNEL_ID:
        try:
            channel = bot.get_channel(ALERT_CHANNEL_ID)
            if channel:
                logger.info(f"Alert channel found: #{channel.name}")
            else:
                logger.warning(f"Alert channel with ID {ALERT_CHANNEL_ID} not found")
        except Exception as e:
            logger.error(f"Error checking alert channel: {e}")

@bot.command(name="temp")
async def send_temp(ctx):
    """Send the latest temperature and humidity readings"""
    if not sensor_data:
        await ctx.send("No data available yet!")
        return
    
    latest = sensor_data[-1]
    timestamp = latest["time"].strftime("%Y-%m-%d %H:%M:%S")
    
    await ctx.send(
        f"🌡️ **Weather Station Report**\n"
        f"🕒 Time: {timestamp}\n"
        f"🌡️ Temperature: {latest['temp']:.1f}°C\n"
        f"💧 Humidity: {latest['hum']:.1f}%"
    )

@bot.command(name="plot")
async def send_plot(ctx, hours: int = 24):
    """Generate and send a plot of temperature and humidity data"""
    if not sensor_data:
        await ctx.send("No data available to plot!")
        return
    
    if hours <= 0:
        await ctx.send("Please specify a positive number of hours.")
        return
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(sensor_data)
    
    # Filter data for requested time period
    cutoff_time = pd.Timestamp.now() - pd.Timedelta(hours=hours)
    df = df[df["time"] >= cutoff_time]
    
    if df.empty:
        await ctx.send(f"No data available for the last {hours} hours.")
        return
    
    # Create plot
    plt.figure(figsize=(10, 6))
    
    # Plot temperature
    ax1 = plt.gca()
    ax1.plot(df["time"], df["temp"], 'r-', label="Temperature (°C)")
    ax1.set_ylabel("Temperature (°C)", color='r')
    ax1.tick_params(axis='y', labelcolor='r')
    
    # Plot humidity on secondary y-axis
    ax2 = ax1.twinx()
    ax2.plot(df["time"], df["hum"], 'b-', label="Humidity (%)")
    ax2.set_ylabel("Humidity (%)", color='b')
    ax2.tick_params(axis='y', labelcolor='b')
    
    # Add title and formatting
    plt.title(f"Weather Data - Last {hours} Hours")
    plt.grid(True, alpha=0.3)
    
    # Format x-axis to show readable dates
    plt.gcf().autofmt_xdate()
    
    # Add legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    # Save to buffer
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    
    # Send file
    await ctx.send(
        f"📊 **Weather data for the last {hours} hours:**", 
        file=discord.File(buf, "weather_plot.png")
    )
    plt.close()

# Method 2: Using Pandas rolling window
@bot.command(name="plot_rolling")
async def send_plot_rolling(ctx, hours: int = 24, window: int = 5):
    """Generate and send a plot with rolling average smoothing
    
    Parameters:
    - hours: Number of hours to display data for
    - window: Window size for rolling average (default: 5)
    """
    if not sensor_data:
        await ctx.send("No data available to plot!")
        return
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(sensor_data)
    
    # Filter data for requested time period
    cutoff_time = pd.Timestamp.now() - pd.Timedelta(hours=hours)
    df = df[df["time"] >= cutoff_time]
    
    if df.empty or len(df) < window:
        await ctx.send(f"Not enough data available for the last {hours} hours to use window size {window}.")
        return
    
    # Sort by time
    df = df.sort_values("time")
    
    # Calculate rolling averages
    df['temp_smooth'] = df['temp'].rolling(window=window, center=True).mean()
    df['hum_smooth'] = df['hum'].rolling(window=window, center=True).mean()
    
    # Forward fill NaN values at the edges
    df['temp_smooth'] = df['temp_smooth'].fillna(method='ffill').fillna(method='bfill')
    df['hum_smooth'] = df['hum_smooth'].fillna(method='ffill').fillna(method='bfill')
    
    # Create plot
    plt.figure(figsize=(10, 6))
    
    # Plot temperature
    ax1 = plt.gca()
    ax1.plot(df["time"], df["temp"], 'r-', alpha=0.3, label="Raw Temperature (°C)")
    ax1.plot(df["time"], df["temp_smooth"], 'r-', linewidth=2, label="Smoothed Temperature (°C)")
    ax1.set_ylabel("Temperature (°C)", color='r')
    ax1.tick_params(axis='y', labelcolor='r')
    
    # Plot humidity on secondary y-axis
    ax2 = ax1.twinx()
    ax2.plot(df["time"], df["hum"], 'b-', alpha=0.3, label="Raw Humidity (%)")
    ax2.plot(df["time"], df["hum_smooth"], 'b-', linewidth=2, label="Smoothed Humidity (%)")
    ax2.set_ylabel("Humidity (%)", color='b')
    ax2.tick_params(axis='y', labelcolor='b')
    
    # Add title and formatting
    plt.title(f"Weather Data - Last {hours} Hours (Rolling Average, Window={window})")
    plt.grid(True, alpha=0.3)
    
    # Format x-axis to show readable dates
    plt.gcf().autofmt_xdate()
    
    # Add legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    # Save to buffer
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    
    # Send file
    await ctx.send(
        f"📊 **Smoothed weather data (rolling average) for the last {hours} hours:**", 
        file=discord.File(buf, "weather_rolling.png")
    )
    plt.close()

@bot.command(name="plot_savgol")
async def send_plot_savgol(ctx, hours: int = 24, window: int = 7, poly: int = 3):
    """Generate and send a plot with Savitzky-Golay smoothing
    
    Parameters:
    - hours: Number of hours to display data for
    - window: Window size (must be odd, default: 7)
    - poly: Polynomial order (default: 3)
    """
    if not sensor_data:
        await ctx.send("No data available to plot!")
        return
    
    # Make sure window is odd
    if window % 2 == 0:
        window = window + 1
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(sensor_data)
    
    # Filter data for requested time period
    cutoff_time = pd.Timestamp.now() - pd.Timedelta(hours=hours)
    df = df[df["time"] >= cutoff_time]
    
    if df.empty or len(df) <= window:
        await ctx.send(f"Not enough data available for the last {hours} hours to use window size {window}.")
        return
    
    # Sort by time
    df = df.sort_values("time")
    
    try:
        from scipy.signal import savgol_filter
        
        # Apply Savitzky-Golay filter
        df['temp_smooth'] = savgol_filter(df['temp'], window_length=window, polyorder=poly)
        df['hum_smooth'] = savgol_filter(df['hum'], window_length=window, polyorder=poly)
        
        # Create plot
        plt.figure(figsize=(10, 6))
        
        # Plot temperature
        ax1 = plt.gca()
        ax1.plot(df["time"], df["temp"], 'r-', alpha=0.3, label="Raw Temperature (°C)")
        ax1.plot(df["time"], df["temp_smooth"], 'r-', linewidth=2, label="Smoothed Temperature (°C)")
        ax1.set_ylabel("Temperature (°C)", color='r')
        ax1.tick_params(axis='y', labelcolor='r')
        
        # Plot humidity on secondary y-axis
        ax2 = ax1.twinx()
        ax2.plot(df["time"], df["hum"], 'b-', alpha=0.3, label="Raw Humidity (%)")
        ax2.plot(df["time"], df["hum_smooth"], 'b-', linewidth=2, label="Smoothed Humidity (%)")
        ax2.set_ylabel("Humidity (%)", color='b')
        ax2.tick_params(axis='y', labelcolor='b')
        
        # Add title and formatting
        plt.title(f"Weather Data - Last {hours} Hours (Savitzky-Golay, Window={window})")
        plt.grid(True, alpha=0.3)
        
        # Format x-axis to show readable dates
        plt.gcf().autofmt_xdate()
        
        # Add legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        # Save to buffer
        buf = BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        
        # Send file
        await ctx.send(
            f"📊 **Smoothed weather data (Savitzky-Golay) for the last {hours} hours:**", 
            file=discord.File(buf, "weather_savgol.png")
        )
        plt.close()
    except Exception as e:
        await ctx.send(f"Error applying Savitzky-Golay filter: {e}")

@bot.command(name="stats")
async def send_stats(ctx, hours: int = 24):
    """Send statistics about the temperature and humidity data"""
    if not sensor_data:
        await ctx.send("No data available yet!")
        return
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(sensor_data)
    
    # Filter data for requested time period
    cutoff_time = pd.Timestamp.now() - pd.Timedelta(hours=hours)
    df = df[df["time"] >= cutoff_time]
    
    if df.empty:
        await ctx.send(f"No data available for the last {hours} hours.")
        return
    
    # Calculate statistics
    temp_min = df["temp"].min()
    temp_max = df["temp"].max()
    temp_avg = df["temp"].mean()
    
    hum_min = df["hum"].min()
    hum_max = df["hum"].max()
    hum_avg = df["hum"].mean()
    
    # Send statistics
    await ctx.send(
        f"📊 **Weather Statistics (Last {hours} hours)**\n\n"
        f"**Temperature:**\n"
        f"- Minimum: {temp_min:.1f}°C\n"
        f"- Maximum: {temp_max:.1f}°C\n"
        f"- Average: {temp_avg:.1f}°C\n\n"
        f"**Humidity:**\n"
        f"- Minimum: {hum_min:.1f}%\n"
        f"- Maximum: {hum_max:.1f}%\n"
        f"- Average: {hum_avg:.1f}%"
    )

@bot.command(name="sulcata_status")
async def sulcata_status(ctx):
    """Send status information about conditions for a sulcata tortoise"""
    if not sensor_data:
        await ctx.send("No data available yet!")
        return
    
    latest = sensor_data[-1]
    temp = latest["temp"]
    hum = latest["hum"]
    
    # Determine temperature status
    if temp < SULCATA_ENV["temp_min"]:
        temp_status = "❄️ **TOO COLD!** Your sulcata needs more heat immediately!"
        temp_advice = "Turn on heating equipment and monitor temperature closely."
    elif temp < SULCATA_ENV["temp_ideal_min"]:
        temp_status = "🥶 **Too Cool** - Below ideal temperature"
        temp_advice = "Consider providing additional heat source."
    elif temp <= SULCATA_ENV["temp_ideal_max"]:
        temp_status = "✅ **Perfect** - Ideal temperature range"
        temp_advice = "Temperature is perfect for your sulcata."
    elif temp <= SULCATA_ENV["temp_max"]:
        temp_status = "🥵 **Too Warm** - Above ideal temperature"
        temp_advice = "Consider providing shade/cooling."
    else:
        temp_status = "🔥 **TOO HOT!** Your sulcata needs cooling immediately!"
        temp_advice = "Move to cooler area or provide shade/cooling immediately!"
    
    # Determine humidity status
    if hum < SULCATA_ENV["hum_min"]:
        hum_status = "🏜️ **Too Dry** - Below ideal humidity"
        hum_advice = "Consider misting or providing humid hide."
    elif hum <= SULCATA_ENV["hum_max"]:
        hum_status = "✅ **Perfect** - Ideal humidity range"
        hum_advice = "Humidity is perfect for your sulcata."
    else:
        hum_status = "💧 **Too Humid** - Above ideal humidity"
        hum_advice = "Provide better ventilation or drier areas."
    
    # Create message
    timestamp = latest["time"].strftime("%Y-%m-%d %H:%M:%S")
    
    await ctx.send(
        f"🐢 **Sulcata Tortoise Environment Status** (as of {timestamp})\n\n"
        f"**Temperature: {temp:.1f}°C ({(temp * 9/5 + 32):.1f}°F)**\n"
        f"{temp_status}\n"
        f"{temp_advice}\n\n"
        f"**Humidity: {hum:.1f}%**\n"
        f"{hum_status}\n"
        f"{hum_advice}\n\n"
        f"**Ideal Environment:**\n"
        f"Temperature: {SULCATA_ENV['temp_ideal_min']}-{SULCATA_ENV['temp_ideal_max']}°C "
        f"({SULCATA_ENV['temp_ideal_min'] * 9/5 + 32:.1f}-{SULCATA_ENV['temp_ideal_max'] * 9/5 + 32:.1f}°F)\n"
        f"Humidity: {SULCATA_ENV['hum_min']}-{SULCATA_ENV['hum_max']}%"
    )

@bot.command(name="set_alerts")
async def set_alerts(ctx):
    """Set the current channel for alerts"""
    global ALERT_CHANNEL_ID
    ALERT_CHANNEL_ID = ctx.channel.id
    
    await ctx.send(
        f"✅ Alert channel set to **#{ctx.channel.name}**\n"
        f"You will receive alerts in this channel when conditions are not suitable for your sulcata tortoise."
    )
    
    logger.info(f"Alert channel set to {ctx.channel.id} (#{ctx.channel.name})")
    
    # Send an immediate status update
    await sulcata_status(ctx)

@bot.command(name="help_weather")
async def help_command(ctx):
    """Send help information about available commands"""
    help_text = (
        "**Weather Station Bot Commands:**\n\n"
        "- `!temp` - Show current temperature and humidity\n"
        "- `!sulcata_status` - Check if conditions are suitable for sulcata tortoise\n"
        "- `!set_alerts` - Set current channel for automatic alerts\n"
        "- `!plot [hours]` - Generate a plot for the specified hours (default: 24)\n"
        "- `!stats [hours]` - Show statistics for the specified hours (default: 24)\n"
        "- `!help_weather` - Show this help message"
    )
    await ctx.send(help_text)

# --- FastAPI Endpoints ---

@app.get("/")
async def root():
    """Root endpoint - provides basic API information"""
    return {
        "message": "Weather Station API is running",
        "endpoints": {
            "/update": "POST - Update sensor data",
            "/data": "GET - Get sensor data",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "data_points": len(sensor_data)
    }

async def check_conditions_and_alert(temp: float, hum: float):
    """Check if conditions are suitable for sulcata tortoise and send alert if needed"""
    global last_alert_time
    current_time = time.time()
    
    # Skip if no alert channel is set or if cooldown hasn't expired
    if not ALERT_CHANNEL_ID or (current_time - last_alert_time < ALERT_COOLDOWN):
        return
        
    alert_needed = False
    alert_message_parts = ["🚨 **SULCATA ALERT** 🚨\n"]
    
    # Check temperature
    if temp < SULCATA_ENV["temp_min"]:
        alert_needed = True
        alert_message_parts.append(
            f"❄️ **TEMPERATURE TOO LOW!**\n"
            f"Current: {temp:.1f}°C ({temp * 9/5 + 32:.1f}°F)\n"
            f"Minimum safe: {SULCATA_ENV['temp_min']}°C ({SULCATA_ENV['temp_min'] * 9/5 + 32:.1f}°F)\n"
            f"Action needed: Provide heat source immediately!\n"
        )
    elif temp > SULCATA_ENV["temp_max"]:
        alert_needed = True
        alert_message_parts.append(
            f"🔥 **TEMPERATURE TOO HIGH!**\n"
            f"Current: {temp:.1f}°C ({temp * 9/5 + 32:.1f}°F)\n"
            f"Maximum safe: {SULCATA_ENV['temp_max']}°C ({SULCATA_ENV['temp_max'] * 9/5 + 32:.1f}°F)\n"
            f"Action needed: Provide cooling/shade immediately!\n"
        )
        
    # Check humidity (only alert for extreme conditions)
    if hum < SULCATA_ENV["hum_min"] - 10:  # More than 10% below minimum
        alert_needed = True
        alert_message_parts.append(
            f"🏜️ **HUMIDITY TOO LOW!**\n"
            f"Current: {hum:.1f}%\n"
            f"Recommended minimum: {SULCATA_ENV['hum_min']}%\n"
            f"Action needed: Mist enclosure or provide humid hide!\n"
        )
    elif hum > SULCATA_ENV["hum_max"] + 15:  # More than 15% above maximum
        alert_needed = True
        alert_message_parts.append(
            f"💧 **HUMIDITY TOO HIGH!**\n"
            f"Current: {hum:.1f}%\n"
            f"Recommended maximum: {SULCATA_ENV['hum_max']}%\n"
            f"Action needed: Improve ventilation!\n"
        )
    
    # Send alert if needed
    if alert_needed:
        try:
            channel = bot.get_channel(ALERT_CHANNEL_ID)
            if channel:
                alert_message = "\n".join(alert_message_parts)
                await channel.send(alert_message)
                logger.info(f"Alert sent to channel #{channel.name}")
                last_alert_time = current_time
        except Exception as e:
            logger.error(f"Error sending alert: {e}")

@app.post("/update")
async def update_data(request: Request):
    """Endpoint for ESP8266 to send sensor data"""
    try:
        data = await request.json()
        
        # Validate required fields
        required_fields = ["temp", "hum"]
        for field in required_fields:
            if field not in data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Add timestamp
        entry = {
            "temp": float(data["temp"]),
            "hum": float(data["hum"]),
            "time": pd.Timestamp.now()
        }
        
        # Add any extra fields from the request
        for key, value in data.items():
            if key not in entry and key not in ["time"]:
                entry[key] = value
        
        # Add to data store
        sensor_data.append(entry)
        
        # Trim data if exceeding maximum
        if len(sensor_data) > MAX_DATA_POINTS:
            sensor_data[:] = sensor_data[-MAX_DATA_POINTS:]
        
        # Save to file periodically (every 10 entries)
        if len(sensor_data) % 10 == 0:
            save_sensor_data()
            
        logger.info(f"Received data: Temp={entry['temp']:.1f}°C, Hum={entry['hum']:.1f}%")
        
        # Check conditions and send alert if needed
        await check_conditions_and_alert(entry["temp"], entry["hum"])
        
        # Return tortoise status in the response
        tortoise_status = {
            "temp_status": "ok" if SULCATA_ENV["temp_ideal_min"] <= entry["temp"] <= SULCATA_ENV["temp_ideal_max"] else "warning",
            "hum_status": "ok" if SULCATA_ENV["hum_min"] <= entry["hum"] <= SULCATA_ENV["hum_max"] else "warning"
        }
        
        return {
            "status": "OK", 
            "message": "Data received",
            "tortoise_status": tortoise_status
        }
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data")
async def get_data(hours: Optional[int] = None, limit: Optional[int] = 100):
    """Endpoint to retrieve sensor data"""
    if not sensor_data:
        return {"data": []}
    
    # Copy data to avoid modifying the original
    data = sensor_data.copy()
    
    # Filter by time if hours parameter is provided
    if hours:
        cutoff = pd.Timestamp.now() - pd.Timedelta(hours=hours)
        data = [entry for entry in data if entry["time"] >= cutoff]
    
    # Limit the number of results
    data = data[-limit:]
    
    # Convert pd.Timestamp to string for JSON serialization
    result = [
        {**item, "time": item["time"].isoformat()} 
        for item in data
    ]
    
    return {"data": result}

# Run bot and server together
async def run_bot():
    """Run the Discord bot"""
    try:
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

@app.on_event("startup")
async def startup_event():
    """Run on FastAPI startup"""
    # Load existing data
    load_sensor_data()
    
    # Start the bot
    asyncio.create_task(run_bot())
    logger.info("Server and bot started")

@app.on_event("shutdown")
async def shutdown_event():
    """Run on FastAPI shutdown"""
    # Save data
    save_sensor_data()
    logger.info("Server shutting down, data saved")

# Main entry point
if __name__ == "__main__":
    import uvicorn
    
    # Load existing data before starting
    load_sensor_data()
    
    # Run the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=8000)