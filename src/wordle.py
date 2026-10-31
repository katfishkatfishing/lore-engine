import json
import discord
from src.database import genai_client

class Wordle:
    def __init__(self):
        self.word = ""
        self.meaning = ""
        self.example = ""
        self.solved = False
        self.guesses = []
        self.player_tries = {}

    # get insane word from gemini
    def generate_word(self):
        prompt = """
        Generate an extremely obscure, difficult, long, real English word (at least 7+ letters long). Return only a raw .JSON object with these exact keys: "word", "meaning", "example". Do not include markdown blocks or extra text."""
        response = genai_client.models.generate_content(
            model = 'gemini-3.5-flash-lite',
            contents = prompt
        )
    
        # clean markdown if gemini gives any
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()

        data = json.loads(raw_text)
        self.word = data["word"].upper()
        self.meaning = data["meaning"]
        self.example = data["example"]
        self.solved = False
        self.guesses = []
        self.player_tries = {}

    def evaluate_guess(self, guess: str, user: discord.Member) -> str:
        guess = guess.upper()
        target = self.word

        # 3 tries per person
        tries_used = self.player_tries.get(user.id, 0)
        if tries_used >= 3:
            return f"❌ Pay up for more gemini tokens boi, {user.mention}! "

        # length requirement
        if len(guess) != len(target):
            return f"⚠️ Blind ah can't see how many words?"

        # use a try
        self.player_tries[user.id] = tries_used + 1

        # calc wordle blocks
        result = ["⬛"] * len(target)
        target_counts = {}
        for char in target:
            target_counts[char] = target_counts.get(char, 0) + 1

        # match
        for i in range(len(target)):
            if guess[i] == target[i]:
                result[i] = "🟩"
                target_counts[guess[i]] -= 1 

        # yellow
        for i in range(len(target)):
            if result[i] == "🟩":
                continue
            if guess[i] in target_counts and target_counts[guess[i]] > 0:
                result[i] = "🟨"
                target_counts[guess[i]] -= 1
                
        blocks = "".join(result)
        formatted_guess = f"{user.display_name}: `{guess}`\n{blocks}"
        self.guesses.append(formatted_guess)

        # check win con
        if guess == target:
            self.solved = True
            return self.get_win_board(user)

        # check team limit
        if len(self.guesses) >= 12:
            self.solved = True
            return self.get_lose_board(user)

        return self.get_current_board()

    def get_current_board(self) -> str:
        board = "\n\n".join(self.guesses) if self.guesses else "*No guesses eh*"
        team_tries_left = 12 - len(self.guesses)
        return f"**Impossible Wordle**\n*Word length: {len(self.word)} letters*\n\n{board}"

    def get_win_board(self, winner: discord.Member) -> str:
        board = "\n\n".join(self.guesses)
        reveal = f"🎉**GOT IT!** {winner.mention} cracked!!!"
        reveal += f"📖**{self.word}**: {self.meaning}\n"
        reveal += f"**🗣️*Example: {self.example}*\n\n"
        reveal += f"**Final Board:**\n{board}"
        return reveal

    def get_lose_board(self, user: discord.Member) -> str:
        self.solved = True
        board = "\n\n".join(self.guesses) if self.guesses else "*No guesses made.*"
        reveal = f"🏳️**LOSE!** {user.mention} Team not enuf IQ dawg.\n\n"
        reveal += f"📖**{self.word}**: {self.meaning}\n"
        reveal += f"**🗣️*Example: {self.example}*\n\n"
        reveal += f"**Final Board:**\n{board}"
        return reveal

game_state = Wordle()