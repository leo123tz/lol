"""Build roblox/R6Locomotion_Install.rbxmx: one Studio file with the scripts, config and both
KeyframeSequences.  usage: python3 roblox/build_install.py"""
import os
import xml.etree.ElementTree as ET

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SRC = os.path.join(ROOT, "roblox", "src")
n = [0]


def ref():
    n[0] += 1
    return f"RBXINST{n[0]:06d}"


def folder(name, kids):
    return f'<Item class="Folder" referent="{ref()}"><Properties><string name="Name">{name}</string></Properties>{kids}</Item>'


def script(cls, name, src):
    assert "]]>" not in src
    return (f'<Item class="{cls}" referent="{ref()}"><Properties><string name="Name">{name}</string>'
            f'<ProtectedString name="Source"><![CDATA[{src}]]></ProtectedString></Properties></Item>')


def sequence(path):
    s = open(path, encoding="utf-8").read()
    return s[s.index('<Item class="KeyframeSequence"'):s.rindex("</roblox>")]


README = """-- HOW TO INSTALL (Roblox Studio)
-- 1. Drag the folder 'LocomotionAnimation' into ReplicatedStorage.
-- 2. Drag the LocalScript 'LocomotionAnimator' into StarterPlayer > StarterCharacterScripts.
-- 3. Delete this 'R6Locomotion_Install' folder.
-- Press Play: walking/running works in Studio right away (temporary Studio-only animations).
-- For the live game: right-click LocomotionAnimation > Sources > R6_Walk > 'Save to Roblox',
--    choose your group as the creator, copy the ID, paste it into Config (WalkAnimationId).
--    Do the same for R6_Run (RunAnimationId). Then publish the game.
"""

if __name__ == "__main__":
    cfg = open(os.path.join(SRC, "ReplicatedStorage", "LocomotionAnimation", "Config.lua"), encoding="utf-8").read()
    ctl = open(os.path.join(SRC, "StarterPlayer", "StarterCharacterScripts", "LocomotionAnimator.client.lua"), encoding="utf-8").read()
    srcs = os.path.join(SRC, "ReplicatedStorage", "LocomotionAnimation", "Sources")
    body = folder("R6Locomotion_Install",
                  script("ModuleScript", "README", README)
                  + folder("LocomotionAnimation", script("ModuleScript", "Config", cfg)
                           + folder("Sources", sequence(os.path.join(srcs, "R6_Walk.rbxmx")) + sequence(os.path.join(srcs, "R6_Run.rbxmx"))))
                  + script("LocalScript", "LocomotionAnimator", ctl))
    xml = ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">' + body + "</roblox>")
    ET.fromstring(xml)  # well-formed check
    out = os.path.join(ROOT, "roblox", "R6Locomotion_Install.rbxmx")
    open(out, "w", encoding="utf-8").write(xml)
    print("wrote", out)
