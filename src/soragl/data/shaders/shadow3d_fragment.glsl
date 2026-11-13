#version 330 core

uniform sampler2D u_texture;
uniform bool u_sprite;
uniform float u_alpha_cutoff;

in vec2 v_uv;

void main() {
    if (u_sprite && texture(u_texture, v_uv).a < u_alpha_cutoff) discard;
}
