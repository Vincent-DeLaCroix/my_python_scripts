import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import threading
import os
from datetime import datetime
from gtts import gTTS
import tempfile
import os
import pygame
from pydub import AudioSegment

class OllamaGUI:
    def __init__(self, root):
        print("Initializing GUI...")
        self.root = root
        self.root.title("Ollama Prompt GUI")

        # Initialize pygame mixer for audio playback
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
        self.is_speaking = True  # Set to True by default
        self.temp_audio_file = None
        
        # TTS settings
        self.language = 'en'
        self.tld = 'co.uk'  # Using UK English voice
        
        # Initialize variables
        self.convo_dir = "Ai_Daily_Convo"
        self.current_model = None
        self.conversation_history = ""

        # Ensure conversation directory exists
        os.makedirs(self.convo_dir, exist_ok=True)

        # GUI Layout
        self.setup_gui()

        # Fetch available models
        self.models = self.get_ollama_models()
        if not self.models:
            messagebox.showerror("Error", "No Ollama models found. Please install a model using 'ollama pull <model>'.")
            root.destroy()
            return

        self.model_menu['values'] = self.models
        # Set llama2-uncensored:latest as default if available
        default_model = "llama2-uncensored:latest"
        if default_model in self.models:
            self.model_var.set(default_model)
        else:
            self.model_var.set(self.models[0])  # Fallback to first model if default not found
        self.load_conversation_for_model(self.model_var.get())

    def setup_gui(self):
        # Left Panel for Saved Conversations
        self.left_frame = tk.Frame(self.root, width=200, bg="#f0f0f0")
        self.left_frame.pack(fill="y", side="left")

        tk.Label(self.left_frame, text="Saved Conversations", bg="#f0f0f0").pack(pady=5)
        self.convo_listbox = tk.Listbox(self.left_frame)
        self.convo_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.convo_listbox.bind("<<ListboxSelect>>", self.load_selected_conversation)

        # Right Panel for Model Selection, Prompt, and Response
        self.right_frame = tk.Frame(self.root)
        self.right_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Model Selection
        tk.Label(self.right_frame, text="Select Model:").pack(anchor="w")
        self.model_var = tk.StringVar()
        self.model_menu = ttk.Combobox(self.right_frame, textvariable=self.model_var, state="readonly")
        self.model_menu.pack(fill="x", pady=5)
        self.model_menu.bind("<<ComboboxSelected>>", self.on_model_change)

        # Prompt Entry
        tk.Label(self.right_frame, text="Prompt:").pack(anchor="w")
        self.prompt_text = tk.Text(self.right_frame, height=5, wrap="word")
        self.prompt_text.pack(fill="both", expand=True, pady=5)
        self.create_context_menu(self.prompt_text)

        self.prompt_text.bind("<Return>", self.send_prompt_on_enter)

        # Response Display
        tk.Label(self.right_frame, text="Response:").pack(anchor="w")
        self.response_text = tk.Text(self.right_frame, height=10, wrap="word", state="disabled")
        self.response_text.pack(fill="both", expand=True, pady=5)
        self.create_context_menu(self.response_text)

        # Buttons
        button_frame = tk.Frame(self.right_frame)
        button_frame.pack(pady=5)

        self.send_button = tk.Button(button_frame, text="Send Prompt", command=self.send_prompt)
        self.send_button.pack(side="left", padx=5)

        self.copy_button = tk.Button(button_frame, text="Copy Response", command=self.copy_response)
        self.copy_button.pack(side="left", padx=5)

        self.speak_button = tk.Button(button_frame, text="Stop Speaking", command=self.toggle_speech)  # Changed initial text
        self.speak_button.pack(side="left", padx=5)

        self.save_new_button = tk.Button(button_frame, text="Save Conversation", command=self.save_conversation_with_timestamp)
        self.save_new_button.pack(side="left", padx=5)

        self.new_convo_button = tk.Button(button_frame, text="Start New Conversation", command=self.start_new_conversation)
        self.new_convo_button.pack(side="left", padx=5)

        # Reverb Controls Frame
        reverb_frame = tk.LabelFrame(self.right_frame, text="Reverb Settings", padx=5, pady=5)
        reverb_frame.pack(fill="x", pady=5)

        # Delay Slider
        tk.Label(reverb_frame, text="Delay (ms):").pack(anchor="w")
        self.delay_var = tk.IntVar(value=80)
        self.delay_slider = ttk.Scale(reverb_frame, from_=20, to=200, 
                                    variable=self.delay_var, orient="horizontal")
        self.delay_slider.pack(fill="x", pady=2)

        # Decay Slider
        tk.Label(reverb_frame, text="Decay:").pack(anchor="w")
        self.decay_var = tk.DoubleVar(value=0.6)
        self.decay_slider = ttk.Scale(reverb_frame, from_=0.1, to=0.9, 
                                    variable=self.decay_var, orient="horizontal")
        self.decay_slider.pack(fill="x", pady=2)

        # Repeats Slider
        tk.Label(reverb_frame, text="Repeats:").pack(anchor="w")
        self.repeats_var = tk.IntVar(value=2)
        self.repeats_slider = ttk.Scale(reverb_frame, from_=1, to=5, 
                                      variable=self.repeats_var, orient="horizontal")
        self.repeats_slider.pack(fill="x", pady=2)

        # Status Label
        self.status_label = tk.Label(self.right_frame, text="Status: Ready", fg="blue")
        self.status_label.pack(pady=5)

    def toggle_speech(self):
        """Toggle between speaking and stopping speech"""
        if self.is_speaking:
            self.is_speaking = False
            pygame.mixer.music.stop()
            self.speak_button.config(text="Speak Response")
            self.status_label.config(text="Status: Speech stopped", fg="blue")
        else:
            response = self.response_text.get("1.0", "end").strip()
            if response:
                self.is_speaking = True
                self.speak_button.config(text="Stop Speaking")
                self.status_label.config(text="Status: Speaking...", fg="green")
                
                # Run speech in a separate thread to prevent GUI freezing
                threading.Thread(target=self.speak_text, args=(response,), daemon=True).start()
            else:
                messagebox.showwarning("No Response", "There is no response to speak.")

    def add_reverb(self, audio, delay=100, decay=0.5, repeats=3):
        """Add a reverb effect to the audio by creating delayed overlays"""
        reverbed = audio
        current_delay = delay
        current_volume = decay
        
        for _ in range(repeats):
            # Create delayed version of the audio
            delayed = audio._spawn(audio.raw_data[:-current_delay])
            delayed = delayed - (20 * current_volume)  # Reduce volume of echo
            padded = AudioSegment.silent(duration=current_delay) + delayed
            
            # Overlay with original
            reverbed = reverbed.overlay(padded)
            
            # Increase delay and reduce volume for next echo
            current_delay += delay
            current_volume *= decay
            
        return reverbed

    def speak_text(self, text):
        """Speak the given text using Google TTS with reverb effect"""
        try:
            # Play notification sound
            notification = pygame.mixer.Sound('/home/mother/Documents/Mother_Sounds/call_mother.wav')
            notification.play()
            
            # Generate TTS while notification is playing
            # Create temporary files for the audio
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                self.temp_audio_file = temp_file.name

            # Generate speech using Google TTS
            tts = gTTS(text=text, lang=self.language, tld=self.tld, slow=False)
            tts.save(self.temp_audio_file)

            # Load and process audio with PyDub
            audio = AudioSegment.from_mp3(self.temp_audio_file)
            
            # Add custom reverb effect using slider values
            reverb_audio = self.add_reverb(
                audio, 
                delay=self.delay_var.get(),
                decay=self.decay_var.get(),
                repeats=self.repeats_var.get()
            )
            
            # Export processed audio
            reverb_audio.export(self.temp_audio_file, format="mp3")

            # Wait for notification sound to finish
            pygame.time.wait(1000)  # Adjust this value based on your notification sound length

            # Initialize mixer for TTS playback
            pygame.mixer.quit()
            pygame.mixer.init()
            
            # Clean up previous temp files if they exist
            if self.temp_audio_file and os.path.exists(self.temp_audio_file):
                try:
                    os.remove(self.temp_audio_file)
                except:
                    pass

            # Create temporary files for the audio
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                self.temp_audio_file = temp_file.name

            # Generate speech using Google TTS
            tts = gTTS(text=text, lang=self.language, tld=self.tld, slow=False)
            tts.save(self.temp_audio_file)

            # Load audio with PyDub
            audio = AudioSegment.from_mp3(self.temp_audio_file)
            
            # Add custom reverb effect using slider values
            reverb_audio = self.add_reverb(
                audio, 
                delay=self.delay_var.get(),
                decay=self.decay_var.get(),
                repeats=self.repeats_var.get()
            )
            
            # Export processed audio
            reverb_audio.export(self.temp_audio_file, format="mp3")

            # Play the processed audio
            pygame.mixer.music.load(self.temp_audio_file)
            pygame.mixer.music.play()

            # Wait for the audio to finish
            while pygame.mixer.music.get_busy():
                if not self.is_speaking:  # Check if we should stop
                    pygame.mixer.music.stop()
                    break
                pygame.time.Clock().tick(10)

        except Exception as e:
            messagebox.showerror("Speech Error", f"Error during speech: {str(e)}")
        finally:
            if not self.speak_button.cget("text") == "Stop Speaking":
                self.is_speaking = False
            # Clean up temp file
            if self.temp_audio_file and os.path.exists(self.temp_audio_file):
                try:
                    os.remove(self.temp_audio_file)
                except:
                    pass

    
    
    def create_context_menu(self, text_widget):
        """Create a context menu for copy, cut, and paste."""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Cut", command=lambda: text_widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: text_widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: text_widget.event_generate("<<Paste>>"))

        def show_context_menu(event):
            menu.post(event.x_root, event.y_root)

        text_widget.bind("<Button-3>", show_context_menu)

    def get_ollama_models(self):
        """Retrieve a list of installed Ollama models."""
        try:
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            models = [line.split()[0] for line in lines if line]
            return models
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Failed to retrieve models: {e}")
            return []

    def on_model_change(self, event):
        """Handle model change: load the new model's conversation."""
        new_model = self.model_var.get()
        self.load_conversation_for_model(new_model)
        self.current_model = new_model

    def load_conversation_for_model(self, model_name):
        """Load conversation history for the selected model."""
        self.current_model = model_name
        self.conversation_history = ""
        self.update_convo_listbox()
        self.clear_prompt_and_response()

    def save_conversation_with_timestamp(self):
        """Save the current conversation with a timestamp and update the listbox."""
        if not self.current_model:
            messagebox.showwarning("No Model Selected", "Please select a model first.")
            return

        if not self.conversation_history:
            messagebox.showwarning("Empty Conversation", "There is no conversation to save.")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{self.current_model}_{timestamp}.txt"
        filepath = os.path.join(self.convo_dir, filename)

        with open(filepath, "w") as f:
            f.write(self.conversation_history)

        messagebox.showinfo("Conversation Saved", f"Conversation saved as {filename}")
        self.update_convo_listbox()

    def start_new_conversation(self):
        """Save the current conversation and start a new one."""
        self.save_conversation_with_timestamp()
        self.conversation_history = ""
        self.clear_prompt_and_response()
        self.status_label.config(text="Status: New Conversation Started", fg="blue")

    def send_prompt_on_enter(self, event):
        """Send the prompt when the Enter key is pressed."""
        self.send_prompt()
        self.prompt_text.delete("1.0", "end")
        return "break"

    def send_prompt(self):
        new_prompt = self.prompt_text.get("1.0", "end").strip()
        if not new_prompt:
            messagebox.showwarning("Empty Prompt", "Please enter a prompt before sending.")
            return

        full_prompt = f"{self.conversation_history}\n\n{new_prompt}" if self.conversation_history else new_prompt
        model_name = self.model_var.get()

        self.status_label.config(text="Status: Sending Prompt...", fg="blue")
        threading.Thread(target=self.run_ollama, args=(model_name, full_prompt), daemon=True).start()

    def run_ollama(self, model_name, full_prompt):
        """Run the Ollama subprocess and handle responses."""
        try:
            result = subprocess.run(
                ["ollama", "run", model_name],
                input=full_prompt,
                capture_output=True,
                text=True,
                check=True,
                timeout=60
            )
            response = result.stdout.strip()
            response = response.replace("```", "").rstrip(".")

            self.response_text.config(state="normal")
            self.response_text.delete("1.0", "end")
            self.response_text.insert("1.0", response)
            self.response_text.config(state="disabled")

            self.conversation_history = f"{full_prompt}\n\nResponse:\n{response}"
            self.status_label.config(text="Status: Ready", fg="green")
            
            # Automatically start speaking if speech is enabled
            if self.is_speaking:
                threading.Thread(target=self.speak_text, args=(response,), daemon=True).start()
                self.status_label.config(text="Status: Speaking...", fg="green")

        except subprocess.TimeoutExpired:
            self.status_label.config(text="Status: Timeout", fg="red")
            messagebox.showerror("Error", "The request timed out.")
        except subprocess.CalledProcessError as e:
            self.status_label.config(text="Status: Error", fg="red")
            messagebox.showerror("Error", f"Error running the model:\n{e.stderr}")

    def copy_response(self):
        response = self.response_text.get("1.0", "end").strip()
        if response:
            self.root.clipboard_clear()
            self.root.clipboard_append(response)
            self.root.update()
            messagebox.showinfo("Copied", "Response copied to clipboard.")
        else:
            messagebox.showwarning("No Response", "There is no response to copy.")

    def update_convo_listbox(self):
        """Update the listbox with saved conversations."""
        self.convo_listbox.delete(0, "end")
        files = [f for f in os.listdir(self.convo_dir) if f.startswith(self.current_model)]
        for file in sorted(files):
            self.convo_listbox.insert("end", file)

    def load_selected_conversation(self, event):
        """Load the selected conversation from the listbox."""
        selection = self.convo_listbox.curselection()
        if selection:
            selected_file = self.convo_listbox.get(selection[0])
            file_path = os.path.join(self.convo_dir, selected_file)
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    self.conversation_history = f.read()
                self.clear_prompt_and_response()
                self.response_text.config(state="normal")
                self.response_text.insert("1.0", self.conversation_history)
                self.response_text.config(state="disabled")
            else:
                messagebox.showerror("Error", "Selected file not found.")

    def clear_prompt_and_response(self):
        """Clear the prompt and response areas."""
        self.prompt_text.delete("1.0", "end")
        self.response_text.config(state="normal")
        self.response_text.delete("1.0", "end")
        self.response_text.config(state="disabled")

if __name__ == "__main__":
    print("Starting Ollama GUI...")
    root = tk.Tk()
    app = OllamaGUI(root)
    root.mainloop()
