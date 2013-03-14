import sublime
import sublime_plugin
import os
import re
import xml.etree.ElementTree as etree
import io

EXT_SANESNIPPET  = ".sane-snippet"
EXT_SNIPPET_SANE = ".sane.sublime-snippet"

template      = re.compile(r'''
                                ---%(nl)s               # initial separator, newline {optional}
                                (?P<header>.*?)%(nnl)s  # the header, named group for newline
                                ---%(nl)s               # another separator, newline
                                (?P<content>.*)         # the content - matches till the end of the string
                           ''' % dict(nl=r'(?:\r\n?|\n)', nnl=r'(?P<linesep>\r\n?|\n)'),
                           re.S | re.X)
line_template = re.compile(r'^(?P<key>.*?):\s*(?P<val>.*)$')


def xml_append_node(s, tag, text, **kwargs):
    """This one is tough ..."""

    c = etree.Element(tag, **kwargs)
    c.text = text
    s.append(c)
    return s


def snippet_to_xml(snippet):
    """This one is tougher (btw I'm talking about etree.Elements here) ..."""

    s = etree.Element('snippet')
    for key in ['description', 'tabTrigger', 'scope']:
        xml_append_node(s, key, snippet[key])

    # This used to modify ElementTree to handle CDATA as a node, but that code
    # wasn't reliable between different ElementTree versions. This just
    # lets etree do normal XML escaping, making the XML file harder to read,
    # but you should be reading the the sane version anyway. 
    # TODO: Any funcitonal differences doing this?
    content = etree.Element('content')
    content.text = snippet['content']
    s.append(content)

    return s


def parse_snippet(path, name, text):
    """Parse a .sane-snippet and return an dict with the snippet's data
    May raise SyntaxError (intended) or other unintended exceptions.
    @return dict() with snippet's data"""

    snippet = {
        'path':        path,
        'name':        name,
        'description': name,
        'tabTrigger':  '',
        'scope':       '',
        'linesep':     os.linesep
    }

    def parse_val(text):
        # TODO: handle quoted strings.
        return text.strip()

    match = template.match(text)
    if match is None:
        raise SyntaxError("Unable to parse SaneSnippet")
    m = match.groupdict()
    snippet['content'] = m['content']
    snippet['linesep'] = m['linesep']

    for line in m['header'].splitlines():
        match = line_template.match(line)
        if match is None:
            raise SyntaxError("Unable to parse SaneSnippet header")
        m = match.groupdict()
        m['key'] = m['key'].strip()
        if m['key'] in ('description', 'tabTrigger', 'scope'):
            snippet[m['key']] = parse_val(m['val'])
        else:
            raise SyntaxError('Unexpected SaneSnippet property: "%s"' % m['key'])

    return snippet


def regenerate_snippet(path, onload=False):
    """Call parse_snippet() and be proud of it (and catch some exceptions)
    @return generated XML string or None"""

    (name, ext) = os.path.splitext(os.path.basename(path))
    try:
        f = open(path, 'r')
    except:
        print("SaneSnippet: Unable to read `%s`" % path)
        return None
    else:
        read = f.read()
        f.close()

    try:
        snippet = parse_snippet(path, name, read)
    except Exception as e:
        msg  = isinstance(e, SyntaxError) and str(e) or "Error parsing SaneSnippet"
        msg += " in file `%s`" % path
        if onload:
            # Sublime Text likes "hanging" itself when an error_message is pushed at initialization
            print("Error: " + msg)
        else:
            sublime.error_message(msg)
        if not isinstance(e, SyntaxError):
            print(e)  # print the error only if it's not raised intentionally

        return None

    sio = io.BytesIO()
    try:
        # TODO: Prettify the XML structure before writing
        etree.ElementTree(snippet_to_xml(snippet)).write(sio)
    except Exception as e:
        print("SaneSnippet: Could not write XML data into stream for file `%s`" % path)
        return None
    else:
        s = sio.getvalue().decode('utf-8')

        return s
    finally:
        sio.close()


def regenerate_snippets(root=sublime.packages_path(), onload=False, force=False):
    """Check the `root` dir for EXT_SANESNIPPETs and regenerate them; write only if necessary
    Also delete parsed snippets that have no raw equivalent"""

    for root, dirs, files in os.walk(root):
        for basename in files:
            path = os.path.join(root, basename)
            (name, ext) = os.path.splitext(basename)

            # Remove parsed snippets that have no raw equivalent
            if basename.endswith(EXT_SNIPPET_SANE):
                sane_path = swap_extension(path)
                if not os.path.exists(sane_path):
                    try:
                        os.remove(path)
                    except:
                        print("SaneSnippet: Unable to delete `%s`, file is probably in use" % path)

                continue

            # Create new snippets
            if basename.endswith(EXT_SANESNIPPET):
                (sane_path, path) = (path, swap_extension(path))
                # Generate XML
                generated = regenerate_snippet(sane_path, onload=onload)
                if generated is None:
                    continue  # errors already printed

                # Check if snippet should be written
                write = False
                if force or not os.path.exists(path):
                    write = True
                else:
                    try:
                        f = open(path, 'r')
                    except:
                        print("SaneSnippet: Unable to read `%s`" % path)
                        continue
                    else:
                        read = f.read()
                        f.close()

                    if read != generated:
                        write = True

                # Write the file
                if write:
                    try:
                        f = open(path, 'w')
                    except:
                        print("SaneSnippet: Unable to open `%s`" % path)
                        continue
                    else:
                        read = f.write(generated)
                        f.close()


def swap_extension(path):
    "Swaps `path`'s extension between `EXT_SNIPPET_SANE` and `EXT_SANESNIPPET`"

    if path.endswith(EXT_SNIPPET_SANE):
        return path.replace(EXT_SNIPPET_SANE, EXT_SANESNIPPET)
    else:
        return path.replace(EXT_SANESNIPPET, EXT_SNIPPET_SANE)

# Go go gadget snippets! (run async?)
regenerate_snippets(onload=True)


# Watch for updated snippets
class SaneSnippet(sublime_plugin.EventListener):
    """Rechecks the view's directory for .sane-snippets and regenerates them,
    if the saved file is a .sane-snippet

    Implements:
        on_post_save"""

    def on_post_save(self, view):
        fn = view.file_name()
        if (fn.endswith('.sane-snippet')):
            regenerate_snippets(os.path.dirname(fn))


# A command interface
class RegenerateSaneSnippetsCommand(sublime_plugin.WindowCommand):
    """Rechecks the packages directory for .sane-snippets and regenerates them
    If `force = True` it will regenerate all the snippets even if they weren't updated"""
    def run(self, force=True):
        regenerate_snippets(force=force)
