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
        self.revealed_indices = set()
        self.letter_states = {}

    # letter to emoji
    def _to_emoji(self, char: str) -> str:
        if char.isalpha:
            offset = ord(char.upper()) - ord('A')
            return chr(0x1F1E6 + offset) + '\u200B'
        return char

    # get insane sentence from gemini
    def generate_word(self):
        prompt = """
        Generate an extremely obscure, difficult, and meaningful English sentence (at least 4+ words and at least 20-50 letters long). Return only a raw .JSON object with these exact keys: "word", "meaning", "example". (Put the sentence in the "word" key). Do not include markdown blocks or extra text."""
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
        self.revealed_indices = set()

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
                result[i] = self._to_emoji(guess[i])
                target_counts[guess[i]] -= 1 

        # yellow
        for i in range(len(target)):
            if result[i] == target[i]:
                continue
            if guess[i] in target_counts and target_counts[guess[i]] > 0:
                result[i] = "🟨"
                target_counts[guess[i]] -= 1
                
        blocks = "".join(result)
        formatted_guess = f"{user.display_name}: `{guess}`\n{blocks}"
        self.guesses.append(formatted_guess)

        # check letter states
        for i, char in enumerate(guess): 
            if char.isalpha():
                if result[i] == "🟩":
                    self.letter_states[char] = "🟩"
                elif result[i] == "🟨" and self.letter_states.get(char) != "🟩":
                    self.letter_states[char] = "🟨"
                elif char not in target:
                    self.letter_states[char] = "⬛"

        # check win con
        if guess == target:
            self.solved = True
            return self.get_win_board(user)

        # check team limit
        if len(self.guesses) >= 12:
            self.solved = True
            return self.get_lose_board(user)

        # hint logic
        if len(self.guesses) %2 == 0:
            import random

            unrevealed = [i for i, char in enumerate(self.word) if char.isalpha() and i not in self.revealed_indices]

            total_alpha = sum(1 for char in self.word if char.isalpha())

            num_to_reveal = max(1, total_alpha // 7)

            if unrevealed:
                to_reveal = random.sample(unrevealed, min(num_to_reveal, len(unrevealed)))
                self.revealed_indices.update(to_reveal)

        return self.get_status_board()

    def get_current_board(self) -> str:
        board = "\n\n".join(self.guesses) if self.guesses else "*No guesses eh*"
        team_tries_left = 12 - len(self.guesses)

        clean_words = ''.join(c if c.isalpha() else ' ' for c in self.word).split()
        word_lengths = " - ".join(str(len(w)) for w in clean_words)

        hint_arr = [self._to_emoji(char) if (i in self.revealed_indices and char.isalpha()) else (char if not char.isalpha() else "⬜") for i, char in enumerate(self.word)]
        hint_str = f"\n\n💡 **Word Lengths:** [ {word_lengths} ]\n{''.join(hint_arr)}"

        return f"**Impossible Nerdle**\n*Length: {len(self.word)} characters (with spaces)* | *Team left: {team_tries_left}/12*{hint_str}\n\n{board}"

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

    def get_status_board(self) -> str:
        board = self.get_current_board()

        yellows = [char for char, state in self.letter_states.items() if state == "🟨"]
        deads = [char for char, state in self.letter_states.items() if state == "⬛"]

        yellow_str = ", ".join(sorted(yellows)) if yellows else "*None yet*"
        dead_str = ", ".join(sorted(deads)) if deads else "*None yet*"

        return f"{board}\n\n🟨 **Yellow (In sentence, wrong place):** {yellow_str}\n⬛ **Dead (Not in sentence):** {dead_str}"
    
game_state = Wordle()