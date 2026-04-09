// --- ORIGINAL SERIAL IMPORT (Commented out for future testing) ---
// import processing.serial.*;
// Serial myPort;

// --- NEW WI-FI IMPORT ---
import processing.net.*;
Server myServer;

float robotX = 400; 
float robotY = 400;
float lastX = 400;
float lastY = 400;

void setup() {
  size(800, 800); 
  background(30); 
  
  // --- ORIGINAL SERIAL SETUP (Commented out) ---
  /*
  println("AVAILABLE PORTS:");
  printArray(Serial.list());
  println("-------------------------");
  String portName = "COM7"; 
  try {
    myPort = new Serial(this, portName, 115200); 
    myPort.bufferUntil('\n'); 
    println("Successfully connected to " + portName + "! Waiting for robot...");
  } catch (Exception e) {
    println("ERROR: Could not connect to " + portName + ".");
  }
  */

  // --- NEW WI-FI SETUP ---
  // Start a server on your laptop listening on port 5204
  myServer = new Server(this, 5204); 
  println("Wi-Fi Server Started on Port 5204! Waiting for ESP32 to connect...");
}

void draw() {
  stroke(255, 50, 50); 
  strokeWeight(4);     
  line(lastX, lastY, robotX, robotY);
  
  lastX = robotX;
  lastY = robotY;
  
  // --- NEW: WI-FI DATA READING ---
  Client thisClient = myServer.available();
  
  if (thisClient != null) {
    String inString = thisClient.readStringUntil('\n');
    
    if (inString != null) {
      inString = trim(inString); 
      
      // Check if this is a coordinate message or a diagnostic log
      if (inString.startsWith("DATA:")) {
        
        // Cut off the "DATA:" part to just get the numbers
        String mathPart = inString.substring(5); 
        String[] coords = split(mathPart, ','); 
        
        if (coords.length == 2) {
          float espX = float(coords[0]);
          float espY = float(coords[1]);
          
          robotX = 400 + espX;
          robotY = 400 - espY; 
        }
      } else {
        // It's a normal log! Print it so we can read it.
        println("Log: " + inString); 
      }
    }
  }
}

// --- ORIGINAL SERIAL EVENT (Commented out for future testing) ---
/*
void serialEvent(Serial myPort) {
  String inString = myPort.readStringUntil('\n');
  if (inString != null) {
    inString = trim(inString); 
    if (inString.startsWith("DATA:")) {
      String mathPart = inString.substring(5); 
      String[] coords = split(mathPart, ','); 
      if (coords.length == 2) {
        float espX = float(coords[0]);
        float espY = float(coords[1]);
        robotX = 400 + espX;
        robotY = 400 - espY; 
      }
    } else {
      println("Log: " + inString); 
    }
  }
}
*/

// --- BONUS: PRESS 'S' TO SAVE YOUR ARTWORK! ---
void keyPressed() {
  if (key == 's' || key == 'S') {
    // Saves a PNG to your sketch folder with the exact time so they don't overwrite!
    saveFrame("Robot_Art_Gallery/drawing-####.png");
    println("SUCCESS: Artwork saved to gallery!");
  }
}
