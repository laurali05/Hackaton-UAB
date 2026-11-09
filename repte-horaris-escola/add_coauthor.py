import subprocess

# Emails objetivo a los que añadir tu coautoría
target_emails = [
    "sofia.mirza.chowdhury@gmail.com",
]
coauthor_line = "Co-authored-by: laurali05 <lopeizquierd@gmail.com>"

# Script para bash/sh que usará filter-branch internamente
filter_script = f'''
msg="$(cat)"
for email in {" ".join(target_emails)}; do
    if [ "$GIT_AUTHOR_EMAIL" = "$email" ]; then
        case "$msg" in
            *"Co-authored-by: laurali05"*)
                ;;
            *)
                msg="$(printf "%s\\n\\n{coauthor_line}\\n" "$msg")"
                ;;
        esac
    fi
done
echo "$msg"
'''

with open('.git_filter_msg.sh', 'w', newline='\n') as f:
    f.write(filter_script)

print("Actualizando historial del repositorio...")
cmd = 'git filter-branch -f --msg-filter "sh .git_filter_msg.sh" -- --all'
subprocess.run(cmd, shell=True)

# Limpieza del script temporal
import os
if os.path.exists('.git_filter_msg.sh'):
    os.remove('.git_filter_msg.sh')

print("¡Proceso completado!")