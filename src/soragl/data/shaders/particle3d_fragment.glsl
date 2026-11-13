#version 330 core

uniform bool u_round;

in vec2 v_corner;
in vec4 v_color;

out vec4 f_color;

void main() {
    if (u_round && length(v_corner) > 0.5) discard;
    f_color = v_color;
}
