import processing.net.*;

Server myServer;

// --- Canvas Variables ---
float robotX = 400; 
float robotY = 400;
float lastX = 400;
float lastY = 400;

void setup() {
  size(800, 800); 
  background(30); 
  
  // Start a server on your laptop listening on port 5204
  myServer = new Server(this, 5204); 
  println("Wi-Fi Server Started on Port 5204! Waiting for ESP32 to connect...");
}

void draw() {
  // --- DRAW THE LINE ---
  stroke(255, 50, 50); 
  strokeWeight(4);     
  line(lastX, lastY, robotX, robotY);
  
  lastX = robotX;
  lastY = robotY;
  
  // --- READ WI-FI DATA ---
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

// --- CLOUD PIPELINE CONTROLS ---
void keyPressed() {
  // PRESS 'S' TO SAVE YOUR ARTWORK TO GOOGLE DRIVE
  if (key == 's' || key == 'S') {
    // Saves a PNG with the exact time so they don't overwrite!
    saveFrame("G:/My Drive/Turbo wall climbing robot/drawing-####.png");
    println("SUCCESS: Artwork saved to Google Drive Gallery!");
  }
  
  // PRESS 'C' TO CLEAR THE CANVAS FOR A NEW DRAWING
  else if (key == 'c' || key == 'C') {
    background(30); // Repaint the background gray
    
    // Reset the robot back to the center of the screen
    robotX = 400; 
    robotY = 400; 
    lastX = 400; 
    lastY = 400;
    
    println("Canvas cleared! Ready for a new track.");
  }
}
