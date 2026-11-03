#version 330 core

layout (location = 0) in vec2 in_position;

out vec2 f_uv;

void main() {
    // pygame rows run top to bottom, GL rows bottom to top
    f_uv = vec2(in_position.x * 0.5 + 0.5, 0.5 - in_position.y * 0.5);
    gl_Position = vec4(in_position, 0.0, 1.0);
}
