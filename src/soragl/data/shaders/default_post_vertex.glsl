#version 330 core

layout (location = 0) in vec3 in_position;
layout (location = 1) in vec2 in_texcoords;

out vec2 f_uv;
out float f_tex;

void main() {;
    f_tex = 0.0;
    f_uv = in_texcoords;
    gl_Position = vec4(in_position, 1.0);
}