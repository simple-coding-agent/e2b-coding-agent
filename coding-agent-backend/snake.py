import pygame
import random
import sys
import math

# Initialize pygame
pygame.init()

# Game constants
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
GRID_SIZE = 20
GRID_WIDTH = WINDOW_WIDTH // GRID_SIZE
GRID_HEIGHT = WINDOW_HEIGHT // GRID_SIZE

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
DARK_GREEN = (0, 128, 0)
FOREST_GREEN = (34, 139, 34)  # More vibrant green background
YELLOW = (255, 255, 0)  # Yellow for the sun
BRIGHT_YELLOW = (255, 255, 100)  # Brighter yellow for sun center
ORANGE = (255, 165, 0)  # Orange for sun rays
GOLD = (255, 215, 0)  # Gold color for sun outline
PINK = (255, 192, 203)  # Pink for the tongue

# Directions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)

class Snake:
    def __init__(self):
        self.body = [(GRID_WIDTH // 2, GRID_HEIGHT // 2)]
        self.direction = RIGHT
        self.grow_next = False
        self.tongue_frame = 0  # Animation frame for tongue flicking
    
    def move(self):
        head = self.body[0]
        new_head = (head[0] + self.direction[0], head[1] + self.direction[1])
        self.body.insert(0, new_head)
        
        if not self.grow_next:
            self.body.pop()
        else:
            self.grow_next = False
        
        # Update tongue animation
        self.tongue_frame = (self.tongue_frame + 1) % 20
    
    def grow(self):
        self.grow_next = True
    
    def change_direction(self, new_direction):
        # Prevent the snake from going back into itself
        if (new_direction[0] * -1, new_direction[1] * -1) != self.direction:
            self.direction = new_direction
    
    def check_collision(self):
        head = self.body[0]
        
        # Check wall collision
        if (head[0] < 0 or head[0] >= GRID_WIDTH or 
            head[1] < 0 or head[1] >= GRID_HEIGHT):
            return True
        
        # Check self collision
        if head in self.body[1:]:
            return True
        
        return False
    
    def draw_tongue(self, screen, head_rect):
        """Draw a forked tongue extending from the snake's head"""
        # Only show tongue every few frames for flicking effect
        if self.tongue_frame < 15:  # Tongue visible for 15 frames out of 20
            head_center_x = head_rect.centerx
            head_center_y = head_rect.centery
            
            # Calculate tongue base position (front of the head)
            tongue_base_offset = GRID_SIZE // 3
            if self.direction == RIGHT:
                tongue_base_x = head_rect.right - 2
                tongue_base_y = head_center_y
            elif self.direction == LEFT:
                tongue_base_x = head_rect.left + 2
                tongue_base_y = head_center_y
            elif self.direction == UP:
                tongue_base_x = head_center_x
                tongue_base_y = head_rect.top + 2
            elif self.direction == DOWN:
                tongue_base_x = head_center_x
                tongue_base_y = head_rect.bottom - 2
            
            # Calculate tongue length (varies with animation for flicking effect)
            base_length = GRID_SIZE // 2 + 5
            tongue_length = base_length + (2 * math.sin(self.tongue_frame * 0.5))
            
            # Calculate main tongue end position
            if self.direction == RIGHT:
                tongue_end_x = tongue_base_x + tongue_length
                tongue_end_y = tongue_base_y
            elif self.direction == LEFT:
                tongue_end_x = tongue_base_x - tongue_length
                tongue_end_y = tongue_base_y
            elif self.direction == UP:
                tongue_end_x = tongue_base_x
                tongue_end_y = tongue_base_y - tongue_length
            elif self.direction == DOWN:
                tongue_end_x = tongue_base_x
                tongue_end_y = tongue_base_y + tongue_length
            
            # Draw main tongue line
            pygame.draw.line(screen, PINK, 
                           (tongue_base_x, tongue_base_y), 
                           (tongue_end_x, tongue_end_y), 3)
            
            # Draw forked tips
            fork_length = 6
            fork_angle = 0.5  # Angle for fork spread
            
            if self.direction in [RIGHT, LEFT]:
                # For horizontal movement
                fork1_end_x = tongue_end_x
                fork1_end_y = tongue_end_y - fork_length
                fork2_end_x = tongue_end_x
                fork2_end_y = tongue_end_y + fork_length
            else:
                # For vertical movement
                fork1_end_x = tongue_end_x - fork_length
                fork1_end_y = tongue_end_y
                fork2_end_x = tongue_end_x + fork_length
                fork2_end_y = tongue_end_y
            
            # Draw the two fork tips
            pygame.draw.line(screen, PINK, 
                           (tongue_end_x, tongue_end_y), 
                           (fork1_end_x, fork1_end_y), 2)
            pygame.draw.line(screen, PINK, 
                           (tongue_end_x, tongue_end_y), 
                           (fork2_end_x, fork2_end_y), 2)
    
    def draw(self, screen):
        for i, segment in enumerate(self.body):
            color = DARK_GREEN if i == 0 else GREEN  # Head is darker
            rect = pygame.Rect(segment[0] * GRID_SIZE, segment[1] * GRID_SIZE, 
                             GRID_SIZE, GRID_SIZE)
            pygame.draw.rect(screen, color, rect)
            pygame.draw.rect(screen, BLACK, rect, 2)
            
            # Draw tongue on the head
            if i == 0:
                self.draw_tongue(screen, rect)

class Food:
    def __init__(self):
        self.position = self.generate_position()
    
    def generate_position(self):
        return (random.randint(0, GRID_WIDTH - 1), 
                random.randint(0, GRID_HEIGHT - 1))
    
    def respawn(self, snake_body):
        while True:
            self.position = self.generate_position()
            if self.position not in snake_body:
                break
    
    def draw(self, screen):
        rect = pygame.Rect(self.position[0] * GRID_SIZE, self.position[1] * GRID_SIZE,
                          GRID_SIZE, GRID_SIZE)
        pygame.draw.ellipse(screen, RED, rect)  # Make food circular
        pygame.draw.ellipse(screen, BLACK, rect, 2)

class Sun:
    def __init__(self):
        self.center = (100, 100)  # Position in top-left area
        self.radius = 45
        self.ray_length = 25
        self.inner_radius = 30
        
    def draw(self, screen):
        # Draw extended sun rays (longer rays)
        num_rays = 12
        for i in range(num_rays):
            angle = (2 * math.pi / num_rays) * i
            start_x = self.center[0] + math.cos(angle) * (self.radius - 5)
            start_y = self.center[1] + math.sin(angle) * (self.radius - 5)
            end_x = self.center[0] + math.cos(angle) * (self.radius + self.ray_length)
            end_y = self.center[1] + math.sin(angle) * (self.radius + self.ray_length)
            
            pygame.draw.line(screen, ORANGE, (start_x, start_y), (end_x, end_y), 4)
        
        # Draw shorter rays between the main rays for more detail
        for i in range(num_rays):
            angle = (2 * math.pi / num_rays) * i + (math.pi / num_rays)
            start_x = self.center[0] + math.cos(angle) * (self.radius - 5)
            start_y = self.center[1] + math.sin(angle) * (self.radius - 5)
            end_x = self.center[0] + math.cos(angle) * (self.radius + self.ray_length - 10)
            end_y = self.center[1] + math.sin(angle) * (self.radius + self.ray_length - 10)
            
            pygame.draw.line(screen, GOLD, (start_x, start_y), (end_x, end_y), 2)
        
        # Draw sun body with gradient effect
        pygame.draw.circle(screen, YELLOW, self.center, self.radius)
        pygame.draw.circle(screen, BRIGHT_YELLOW, self.center, self.inner_radius)
        pygame.draw.circle(screen, GOLD, self.center, self.radius, 3)
        
        # Add a small highlight for more dimension
        highlight_center = (self.center[0] - 10, self.center[1] - 10)
        pygame.draw.circle(screen, WHITE, highlight_center, 8)

class SnakeGame:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Enhanced Snake Game - Green World with Forked Tongue")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.sun = Sun()
        self.reset_game()
    
    def reset_game(self):
        self.snake = Snake()
        self.food = Food()
        self.score = 0
        self.game_over = False
        self.paused = False
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            elif event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key == pygame.K_r:
                        self.reset_game()
                    elif event.key == pygame.K_q:
                        return False
                else:
                    if event.key == pygame.K_UP:
                        self.snake.change_direction(UP)
                    elif event.key == pygame.K_DOWN:
                        self.snake.change_direction(DOWN)
                    elif event.key == pygame.K_LEFT:
                        self.snake.change_direction(LEFT)
                    elif event.key == pygame.K_RIGHT:
                        self.snake.change_direction(RIGHT)
                    elif event.key == pygame.K_SPACE:
                        self.paused = not self.paused
        return True
    
    def update(self):
        if not self.game_over and not self.paused:
            self.snake.move()
            
            # Check if snake ate food
            if self.snake.body[0] == self.food.position:
                self.snake.grow()
                self.score += 10
                self.food.respawn(self.snake.body)
            
            # Check for collision
            if self.snake.check_collision():
                self.game_over = True
    
    def draw_grass_pattern(self):
        # Add some simple grass-like pattern to enhance the green background
        grass_color = (20, 100, 20)
        for x in range(0, WINDOW_WIDTH, 40):
            for y in range(0, WINDOW_HEIGHT, 40):
                if random.randint(0, 10) > 7:  # Random grass patches
                    pygame.draw.line(self.screen, grass_color, 
                                   (x + random.randint(0, 35), y + random.randint(0, 35)), 
                                   (x + random.randint(0, 35), y + random.randint(0, 35) + 5), 2)
    
    def draw(self):
        # Fill background with vibrant forest green
        self.screen.fill(FOREST_GREEN)
        
        # Add subtle grass pattern (optional - comment out if too busy)
        # self.draw_grass_pattern()
        
        # Draw the enhanced sun in the top-left corner
        self.sun.draw(self.screen)
        
        if not self.game_over:
            self.snake.draw(self.screen)
            self.food.draw(self.screen)
        
        # Draw score with better visibility
        score_text = self.font.render(f"Score: {self.score}", True, WHITE)
        score_shadow = self.font.render(f"Score: {self.score}", True, BLACK)
        self.screen.blit(score_shadow, (11, 11))  # Shadow for better visibility
        self.screen.blit(score_text, (10, 10))
        
        # Draw game over screen
        if self.game_over:
            # Create a semi-transparent overlay
            overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
            overlay.set_alpha(128)
            overlay.fill(BLACK)
            self.screen.blit(overlay, (0, 0))
            
            game_over_text = self.font.render("GAME OVER", True, WHITE)
            restart_text = self.font.render("Press R to restart or Q to quit", True, WHITE)
            final_score_text = self.font.render(f"Final Score: {self.score}", True, YELLOW)
            
            game_over_rect = game_over_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 70))
            final_score_rect = final_score_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 30))
            restart_rect = restart_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 20))
            
            self.screen.blit(game_over_text, game_over_rect)
            self.screen.blit(final_score_text, final_score_rect)
            self.screen.blit(restart_text, restart_rect)
        
        # Draw pause screen
        if self.paused and not self.game_over:
            overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
            overlay.set_alpha(128)
            overlay.fill(BLACK)
            self.screen.blit(overlay, (0, 0))
            
            pause_text = self.font.render("PAUSED - Press SPACE to continue", True, WHITE)
            pause_rect = pause_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
            self.screen.blit(pause_text, pause_rect)
        
        # Draw instructions with better visibility
        if not self.game_over and not self.paused:
            instructions = self.font.render("Use arrow keys to move, SPACE to pause", True, WHITE)
            instructions_shadow = self.font.render("Use arrow keys to move, SPACE to pause", True, BLACK)
            self.screen.blit(instructions_shadow, (11, WINDOW_HEIGHT - 29))
            self.screen.blit(instructions, (10, WINDOW_HEIGHT - 30))
        
        pygame.display.flip()
    
    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(10)  # 10 FPS for Snake game speed
        
        pygame.quit()
        sys.exit()

# Run the game
if __name__ == "__main__":
    print("Welcome to Enhanced Snake Game - Green World Edition with Forked Tongue!")
    print("Controls:")
    print("- Use arrow keys to move the snake")
    print("- Press SPACE to pause/unpause")
    print("- Press R to restart when game over")
    print("- Press Q to quit when game over")
    print("- Close the window to exit")
    print("\nEnhancements:")
    print("- Vibrant green forest background")
    print("- Enhanced sun with rays and highlights in top-left corner")
    print("- Improved visual elements and text visibility")
    print("- Animated forked tongue that flicks out from the snake's head!")
    print("\nStarting game...")
    
    game = SnakeGame()
    game.run()