import re
import hunspell
import itertools

# Mapping Czech characters to their English equivalents
czech_to_english_map = str.maketrans(
    "áčçďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
    "accdeeinorstuuyzACDEEINORSTUUYZ"
)

# Preprocess text by removing tabs, newlines, and non-ASCII characters,
# converting to lowercase, and replacing Czech characters with English equivalents.
def preprocess_text(text):
    text = text.replace('\t', '').replace('\n', '').replace('\u00A0', ' ').replace("|", "").strip()
    text = text.lower()
    text = text.translate(czech_to_english_map)  # Apply Czech to English conversion
    text = re.sub(r'[^\x00-\x7F]', ' ', text)  # Replace non-ASCII characters with space
    return text

# Initialize Hunspell with the Czech dictionary
hunspell_checker = hunspell.HunSpell('/usr/share/hunspell/cs_CZ.dic', '/usr/share/hunspell/cs_CZ.aff')

# Generate all possible variants of a word by replacing 'i', 'l', and '1' with each other.
def generate_1li_combinations(word):
    substitutions = {
        'i': ['i', 'l', '1'],
        'l': ['i', 'l', '1'],
        '1': ['i', 'l', '1'],
        'r': ['r', 'j'],
        'j': ['r', 'j'],
        'e': ['e', 'o'],
        'o': ['e', 'o'],
    }
    # Find positions of characters in the word that can be substituted
    positions = [i for i, char in enumerate(word) if char in substitutions]

    if not positions:
        return [word]

    # Generate all combinations by substituting at the found positions
    variants = []
    for variant in itertools.product(*[substitutions[word[pos]] for pos in positions]):
        modified_word = list(word)
        for idx, pos in enumerate(positions):
            modified_word[pos] = variant[idx]
        variants.append(''.join(modified_word))

    return variants

# Trie data structure to efficiently store and search words
class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_word = False

class Trie:
    def __init__(self):
        self.root = TrieNode()

    # Insert all variants of a word into the Trie
    def insert(self, word):
        variants = generate_1li_combinations(word)
        for variant in variants:
            node = self.root
            for char in variant:
                if char not in node.children:
                    node.children[char] = TrieNode()
                node = node.children[char]
            node.is_word = True

    # Search for a word in the Trie
    def search(self, word):
        node = self.root
        for char in word:
            if char not in node.children:
                return False
            node = node.children[char]
        return node.is_word

    # Find all valid words in a given text using the Trie
    def find_all_words(self, text):
        """
        Finds all valid word candidates using the trie for the given text.
        Returns a list of tuples (word, start, end), where start and end are indices in the text.
        """
        words = []
        for start in range(len(text)):
            node = self.root
            for end in range(start, len(text)):
                char = text[end]
                if char not in node.children:
                    break
                node = node.children[char]
                if node.is_word:
                    words.append((text[start:end + 1], start, end + 1))
        return words

# Penalize small words to avoid splitting text into short, meaningless words
def calculate_penalty(word):
    if len(word) <= 3:
        return -10  # Penalize very small words
    return len(word)  # Reward longer words

# Dynamic programming function to find the best word combination based on penalties
def best_word_combination(words, text_length):
    dp = [(-float('inf'), [])] * (text_length + 1)
    dp[0] = (0, [])

    for word, start, end in words:
        score = calculate_penalty(word)
        if dp[start][0] + score > dp[end][0]:
            dp[end] = (dp[start][0] + score, dp[start][1] + [word])

    return dp[text_length][1]

# Main function to process a single word by finding valid word combinations
def process_single_word(word, trie):
    # Preprocess the word by removing spaces and converting to lowercase
    concatenated_text = "".join(preprocess_text(word).split())

    # Use the Trie to find all possible valid words in the preprocessed text
    found_words = trie.find_all_words(concatenated_text)

    # Use dynamic programming to find the best combination of words
    best_split = best_word_combination(found_words, len(concatenated_text))

    # Check words in the split against Hunspell dictionary for suggestions if not found in the Trie
    final_processed_words = []
    for word in best_split:
        if not trie.search(word):
            if hunspell_checker.spell(word):
                final_processed_words.append(word)
            else:
                suggestions = hunspell_checker.suggest(word)
                if suggestions:
                    final_processed_words.append(suggestions[0])
                else:
                    final_processed_words.append(word)
        else:
            final_processed_words.append(word)

    # Return the final processed word as a string
    return " ".join(final_processed_words)
