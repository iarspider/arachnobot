import functools

from twitchio.ext import commands


def translate_message(message: str):
    _my_eng_symbols = r"`qwertyuiop[]\asdfghjkl;'zxcvbnm,./" + r'~QWERTYUIOP{}|ASDFGHJKL:"ZXCVBNM<>?' + "@#$^&"
    _my_ru_symbols = r'ёйцукенгшщзхъ\фывапролджэячсмитьбю.' + r"ЁЙЦУКЕНГШЩЗХЪ/ФЫВАПРОЛДЖЭЯЧСМИТЬБЮ," + '"№;:?'

    @functools.cache
    def translator_to_ru():
        return str.maketrans(_my_eng_symbols, _my_ru_symbols)

    @functools.cache
    def translator_to_eng():
        return str.maketrans(_my_ru_symbols, _my_eng_symbols)

    @functools.cache
    def get_only_eng():
        return "".join([i for i in _my_eng_symbols if i not in _my_ru_symbols])

    @functools.cache
    def get_only_ru():
        return "".join([i for i in _my_ru_symbols if i not in _my_eng_symbols])

    translated = []
    for word in message.split(" "):
        eng_count = len(list(filter(lambda x: x in get_only_eng(), word)))
        ru_count = len(list(filter(lambda x: x in get_only_ru(), word)))

        word_translator = translator_to_eng() if ru_count >= eng_count else translator_to_ru()
        translated.append(str.translate(word, word_translator))

    return " ".join(translated)


def twitch_command_aliased(command: str, *args, additional_command: list[str] | tuple[str] = None, **kwargs):
    def decorator(function):
        new_aliases = list(map(translate_message, [command, *additional_command]))
        actual_decorator = commands.command(name=command, aliases=sum([additional_command, new_aliases], start=[]),
                                            *args, **kwargs)
        return actual_decorator(function)

    return decorator
